# -*- coding: utf-8 -*-
"""RunService — оркестрация ядра factory для одного прогона веб-сервиса.

По сути тот же поток, что в factory.flex.main, но: пишет в папку прогона (изоляция по
run_id), берёт LLM и поиск через ИНТЕРФЕЙСЫ (подставляет DI), и складывает результат в
result.json (сериализация как в export.serialize) — из него рендерятся карточки/деталь.

LLM-части (ветка Б, полировка) деградируют мягко: нет доступного LLM → ветка Б
пропускается, детерминированные ветки (хвосты, досье, веб) отдаются как есть.
"""
from __future__ import annotations

import glob
import os
import time

from webapp.infra import storage


def _is_tailings(path: str) -> bool:
    if not path.lower().endswith(".xlsx"):
        return False
    try:
        from factory.reader import TailingsReader
        return len(TailingsReader(path).read().classes) >= 3
    except Exception:  # noqa: BLE001
        return False


def _diagnosis_terms(all_hyps, limit=4) -> str:
    if not all_hyps:
        return ""
    fams = sorted({h.family for h in all_hyps})[:limit]
    forms = sorted({h.dominant_form for h in all_hyps if h.dominant_form})[:limit]
    return " ".join(fams + forms)


class RunService:
    """Собрать материалы прогона → гипотезы (ветки А/Б) + обогащения → result/context/metrics."""

    def __init__(self, llm=None, search=None):
        self.llm = llm            # LLMClient | None
        self.search = search      # SearchClient | None

    def run(self, run_id: str, kpi: str, web_search: bool = False, use_llm: bool = True,
            max_chunks: int = 14, progress=None, log=None) -> dict:
        from factory.client import TELEMETRY
        from factory.export import serialize
        from factory.glossary import write as write_glossary
        from factory.pipeline import HypothesisFactory
        from factory.report import render

        progress = progress or (lambda *a: None)
        log = log or (lambda *a: None)
        use_dossier = use_web = web_search     # «веб-серч» = досье OpenAlex + веб-практики
        self._max_chunks = max_chunks

        TELEMETRY.reset()                       # метрики этого прогона
        progress("Приём материалов")
        rd = storage.ensure_run(run_id)
        src = rd / "sources"

        files = [str(p) for p in src.rglob("*") if p.is_file()]
        tailings = [f for f in sorted(files) if _is_tailings(f)]
        others = [f for f in sorted(files)
                  if f not in tailings and "гипотез" not in os.path.basename(f).lower()]

        # целевой элемент / предупреждение о нём (не выдаём чужой элемент за никель)
        from factory.intent import parse_intent, warn_intent
        intent = parse_intent(kpi)
        warns = []
        skip_a = warn_intent(intent, kpi, emit=warns.append)

        web = dos = None
        if use_web:
            from factory.websearch import WebPractices
            sfn = self.search.search if self.search is not None else None
            web = WebPractices(log=log, search_fn=sfn)
        if use_dossier:
            from factory.openalex import OpenAlexDossier
            dos = OpenAlexDossier(log=log)

        fabrics, all_hyps, reports = [], [], []
        if tailings and not skip_a:
            # три прохода вместо одного перемешанного: этапы на экране загрузки
            # соответствуют тому, что реально происходит (диагностика → веб → рендер)
            progress("Диагностика отчётов")
            diagnosed = []
            for t in tailings:
                res = HypothesisFactory(t, kpi=kpi).run()
                diagnosed.append((res["profile"], res))
                all_hyps.extend(res["hypotheses"])
                log(f"диагностика — {res['profile'].fabric}")
            if diagnosed and (web or dos):
                progress("Поиск в интернете")
                for p, res in diagnosed:
                    hyps = res["hypotheses"]
                    if web:
                        log(f"веб-практики — {p.fabric}")
                        web.enrich(hyps, extra=_diagnosis_terms(hyps))
                    if dos:
                        log(f"досье OpenAlex — {p.fabric}")
                        dos.enrich(hyps)
            for p, res in diagnosed:
                hyps = res["hypotheses"]
                runinfo = {"web": bool(web), "dossier": bool(dos)}
                html = render(p, res["graph"].to_layered(), hyps, kpi=kpi,
                              tech=res.get("tech"), analysis=res.get("analysis"),
                              runinfo=runinfo)
                out = rd / f"{p.fabric}_гипотезы.html"
                out.write_text(html, encoding="utf-8")
                reports.append(out.name)
                fabrics.append((p, hyps, out.name))

        # --- ветка Б (литература) — только если есть неструктурные материалы и доступен LLM ---
        lit_report = None
        llm_ok = bool(self.llm and self.llm.ready and self.llm.probe())
        if others and llm_ok:
            progress("Чтение литературы")
            lit_report = self._branch_b(rd, kpi, intent, others, fabrics, log)
        elif others and not llm_ok:
            log("LLM недоступен — ветка Б пропущена (хвосты/досье/веб готовы)")

        progress("Сборка отчётов")
        write_glossary(str(rd))

        # --- сериализация для рендера карточек + контекст + метрики ---
        result = {"kpi": kpi, "target_element": intent.target_element,
                  "element_in_schema": intent.element_in_schema,
                  "warnings": warns, "fabrics": []}
        for p, hyps, html_name in fabrics:
            data = serialize(hyps, profile=p, kpi=kpi)
            data["report_html"] = html_name
            result["fabrics"].append(data)
        result["literature_report"] = lit_report
        result["reports"] = reports + ([lit_report] if lit_report else [])
        storage.save_json(run_id, "result.json", result)

        ctx = {"kpi": kpi, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
               "enrichments": [k for k, v in {"dossier": use_dossier, "web": use_web,
                                              "литература": bool(lit_report)}.items() if v],
               "tailings_used": [os.path.relpath(t, src) for t in tailings],
               "knowledge_used": [os.path.relpath(o, src) for o in others],
               "reports": result["reports"]}
        storage.save_json(run_id, "context.json", ctx)
        storage.save_json(run_id, "metrics.json", TELEMETRY.snapshot())

        return {"run_id": run_id, "n_fabrics": len(fabrics),
                "n_hypotheses": sum(len(h) for _, h, _ in fabrics),
                "literature": bool(lit_report), "warnings": warns,
                "metrics": TELEMETRY.snapshot()["total"]}

    def _branch_b(self, rd, kpi, intent, others, fabrics, log):
        """Извлечение из текста → граф → разрывы Свонсона → HTML ветки Б (report_kb).
        Плюс подкрепление карточек ветки А цитатами корпуса (litsupport)."""
        from factory.discover import discover
        from factory.extract import extract_relations
        from factory.ingest import ingest, split
        from factory.kgraph import RelationGraph
        from factory.report_kb import render_kb

        ocr = self._ocr()
        chunks = split(ingest(others, ocr=ocr, log=log))
        extra = _diagnosis_terms([h for _, hs, _ in fabrics for h in hs])
        query = f"{kpi} {extra}".strip() if extra else kpi
        cache = str(rd / "kb_cache.json")
        rels = extract_relations(chunks, llm=self.llm,
                                 max_chunks=getattr(self, "_max_chunks", 14),
                                 query=query, cache_path=cache, log=log)

        # подкрепить карточки ветки А цитатами корпуса и пересобрать их HTML
        if rels and fabrics:
            from factory.analysis import analyze
            from factory.knowledge import ProfileGraph
            from factory.litsupport import enrich as lit_enrich
            from factory.report import render
            for p, hyps, html_name in fabrics:
                if lit_enrich(hyps, rels):
                    runinfo = {"web": any(getattr(h, "world_practice", None) for h in hyps),
                               "dossier": any(getattr(h, "dossier", None) for h in hyps)}
                    html = render(p, ProfileGraph(p).to_layered(), hyps, kpi=kpi,
                                  analysis=analyze(p, element=intent.target_element),
                                  runinfo=runinfo)
                    (rd / html_name).write_text(html, encoding="utf-8")

        kg = RelationGraph(rels)
        found = discover(kg, kpi=query, limit=8)
        stats = kg.stats()
        tech = {"фрагментов": len(chunks), "связей в кэше": len(rels),
                "узлов графа": stats["nodes"], "рёбер": stats["edges"]}
        html = render_kb(kg.to_layered(max_nodes=24), found, kpi=kpi, tech=tech)
        name = "литература_гипотезы.html"
        (rd / name).write_text(html, encoding="utf-8")
        return name

    def _ocr(self):
        """OCR-клиент, если включён и реально доступен (preflight), иначе None."""
        try:
            from factory.config import OCR_ENABLED
            if not OCR_ENABLED:
                return None
            from factory.ocr import YandexOCR
            o = YandexOCR()
            return o if (o.ready and o.probe()) else None
        except Exception:  # noqa: BLE001
            return None
