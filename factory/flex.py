# -*- coding: utf-8 -*-
"""Гибкий приём: загрузи ЧТО УГОДНО (папка/файлы) → система разбирается сама.

Диспетчер по типу данных:
  • отчёт по хвостам (xlsx со структурой) → ДЕТЕРМИНИРОВАННАЯ диагностика (factory core);
  • прочий текст (PDF/DOCX/TXT/патенты/статьи) → LLM-извлечение связей (цитатный гейт,
    кэш) → канонический граф → разрывы Свонсона (детерминированно поверх кэша).

Так закрывается требование ТЗ «гибкость входных данных»: детерминизм — в рассуждении,
LLM — только в понимании неструктурированного текста, с заземлением до цитаты/страницы.

Единственная команда, которая СОХРАНЯЕТ конфиг запуска (см. runconfig.py) — так
benchmark.py/judge.py могут переиспользовать этот же KPI без copy-paste, если явно не
передан свой. Единственная команда, которая реально зовёт LLM на извлечение (остальные
только читают кэш).

Если в этом же прогоне нашлась ветка А (хвосты) — запрос к литературе ОБОГАЩАЕТСЯ
терминами уже посчитанного диагноза (семейство вмешательства + минеральная форма),
чтобы искать решения именно под то, что реально нашли в данных, а не по общим словам
KPI. Если ветки А нет (только разрозненная литература/схемы без структурных данных) —
ветка Б работает САМОСТОЯТЕЛЬНО на голом KPI, как раньше — это не регрессия, а честный
fallback.

Запуск:
    uv run python -m factory.flex materials --kpi "снизить потери никеля с хвостами"
    uv run python -m factory.flex materials/knowledge/books --kpi "повысить извлечение Ni"
"""
from __future__ import annotations

import argparse
import os
import time

from factory.config import DEFAULT_CACHE, MIN_PROSE_CHARS, OUTPUTS_DIR, RUN_CONFIG_PATH
from factory.ingest import ingest, split
from factory.runconfig import RunConfig, save_run_config


def _is_tailings(path):
    """Отчёт по хвостам? Пробуем специализированный ридер — есть ли классы крупности."""
    if not path.lower().endswith(".xlsx"):
        return False
    try:
        from factory.reader import TailingsReader
        return len(TailingsReader(path).read().classes) >= 3
    except Exception:  # noqa: BLE001
        return False


def _diagnosis_query_terms(all_hyps, limit=4):
    """Термины уже посчитанного диагноза ветки А — обогатить запрос к литературе.
    Пусто, если гипотез нет (вызывающий код тогда просто не трогает исходный KPI)."""
    if not all_hyps:
        return ""
    fams = sorted({h.family for h in all_hyps})[:limit]
    forms = sorted({h.dominant_form for h in all_hyps if h.dominant_form})[:limit]
    return " ".join(fams + forms)


def main():
    import sys
    try:                                     # печатать сразу построчно, а не пачкой в конце
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="Гибкая фабрика гипотез (загрузи что угодно)")
    ap.add_argument("paths", nargs="+", help="файлы или папки с материалами")
    ap.add_argument("--kpi", required=True, help="обязателен: без цели неясно, что "
                    "оптимизировать и как ранжировать гипотезы")
    ap.add_argument("--max-chunks", type=int, default=14)
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--web", action="store_true",
                    help="искать в интернете мировые практики (world_practice: цитата + URL "
                    "из отраслевых источников, в т.ч. русских соседей; ДЕТЕРМИНИРОВАННО, "
                    "без LLM/ключа; кэшируется)")
    ap.add_argument("--dossier", action="store_true",
                    help="доказательное досье из OpenAlex (реальные статьи + цитируемость "
                    "+ фраза-причина из abstract; БЕЗ LLM, без ключа, кэшируется)")
    ap.add_argument("--run-config", default=RUN_CONFIG_PATH,
                    help="куда сохранить конфиг этого запуска (KPI+параметры) — его "
                    "подхватят benchmark/judge, если им не передать свой --kpi")
    args = ap.parse_args()

    save_run_config(RunConfig(kpi=args.kpi, materials_paths=args.paths,
                              cache_path=args.cache, max_chunks=args.max_chunks,
                              timestamp=time.strftime("%Y-%m-%d %H:%M:%S")),
                    args.run_config)

    # разбираем KPI сразу — чтобы честно предупредить, если целевой элемент не распознан
    # или его нет в схеме отчёта (иначе ветка А молча выдаст никель под видом ответа)
    from factory.intent import parse_intent, warn_intent
    intent = parse_intent(args.kpi)
    skip_branch_a = warn_intent(intent, args.kpi, emit=lambda m: print("\n" + m))

    print("=" * 74)
    print("ГИБКИЙ ПРИЁМ МАТЕРИАЛОВ")
    print(f"KPI: {args.kpi}  (целевой элемент: {intent.target_element}"
          f"{'' if intent.element_in_schema else ' — ВНЕ схемы хвостов'})")
    print(f"конфиг запуска сохранён: {args.run_config} "
          f"(его переиспользуют benchmark/judge без --kpi)")
    print("=" * 74)

    # --- собрать все файлы, отделить отчёты по хвостам от прочего текста ---
    all_files = []
    for p in args.paths:
        if not os.path.exists(p):
            print(f"\nпуть не существует: {p} — пропущен.")
            continue
        if os.path.isdir(p):
            for root, _, fs in os.walk(p):
                all_files += [os.path.join(root, f) for f in fs]
        else:
            all_files.append(p)
    tailings = [f for f in sorted(set(all_files)) if _is_tailings(f)]
    # эталонные «Гипотезы*.docx» — это ОТВЕТЫ, не знание: не кормим их в извлечение
    others = [f for f in sorted(set(all_files))
              if f not in tailings and os.path.isfile(f)
              and "гипотез" not in os.path.basename(f).lower()]

    if not tailings and not others:
        print("\nМАТЕРИАЛОВ НЕ НАЙДЕНО по указанным путям — анализировать нечего.")
        print("  Проверьте пути и положите файлы (Хвосты*.xlsx и/или литературу) туда,")
        print("  на что указывают переданные аргументы.")
        return

    print(f"\nотчётов по хвостам (ветка А, состояние конкретных фабрик): {len(tailings)}")
    print(f"прочих материалов (ветка Б, знание): {len(others)}")

    # --- необязательный веб-поиск мировых практик (заполняет world_practice) ---
    web = None
    if args.web:
        from factory.websearch import WebPractices
        web = WebPractices(log=lambda m: print("  " + m))
        if not web.ready:
            print("\n--web запрошен, но веб-поиск выключен (FACTORY_WEB=0) — "
                  "world_practice останется пустым.")
            web = None

    # --- необязательное доказательное досье OpenAlex (реальные статьи, БЕЗ LLM) ---
    dos = None
    if args.dossier:
        from factory.openalex import OpenAlexDossier
        dos = OpenAlexDossier(log=lambda m: print("  " + m))
        if not dos.ready:
            print("\n--dossier запрошен, но OpenAlex выключен (FACTORY_OPENALEX=0).")
            dos = None

    runinfo = {"web": bool(web), "dossier": bool(dos)}   # что реально запускалось (для отчёта)
    reports = []                                          # пути сгенерированных отчётов

    # --- ветка 1: детерминированная диагностика хвостов ---
    all_hyps = []
    fabric_results = []   # (profile, res, путь HTML) — для дообогащения после извлечения
    if tailings and skip_branch_a:
        print(f"\nдиагностика хвостов пропущена: элемента «{intent.requested_element}» "
              f"нет в отчётах — работает только ветка Б (литература).")
    if tailings and not skip_branch_a:
        from factory.pipeline import HypothesisFactory
        print("\nдетерминированная диагностика хвостов (без LLM):")
        for t in tailings:
            res = HypothesisFactory(t, kpi=args.kpi).run()
            p, hyps = res["profile"], res["hypotheses"]
            all_hyps.extend(hyps)
            # обогащение ДО отрисовки HTML — иначе в отчёт попадёт пустой плейсхолдер
            if web:
                print(f"  веб-поиск мировых практик — {p.fabric}")
                web.enrich(hyps, extra=_diagnosis_query_terms(hyps))
            if dos:
                print(f"  досье OpenAlex — {p.fabric}")
                dos.enrich(hyps)
            if web or dos:
                from factory.report import render
                res["html"] = render(p, res["graph"].to_layered(), hyps, kpi=args.kpi,
                                     tech=res.get("tech"), analysis=res.get("analysis"),
                                     runinfo=runinfo)
            os.makedirs(OUTPUTS_DIR, exist_ok=True)
            out = os.path.join(OUTPUTS_DIR, f"{p.fabric}_гипотезы.html")
            open(out, "w", encoding="utf-8").write(res["html"])
            reports.append(out)
            fabric_results.append((p, res, out))
            top = hyps[0] if hyps else None
            print(f"  {p.fabric}: {len(hyps)} гипотез, топ — "
                  f"{top.statement_if if top else '—'}  [{out}]")

    # --- ветка 2: извлечение из текста → граф → открытие ---
    if others:
        from factory.discover import discover
        from factory.extract import extract_relations
        from factory.kgraph import RelationGraph
        from factory.llm import Yandex
        print("\nизвлечение из текста → граф → разрывы Свонсона (ветка Б):")

        # PREFLIGHT: проверяем доступность LLM и OCR ОТДЕЛЬНО и БЫСТРО (короткий таймаут,
        # без ретраев) ДО тяжёлого приёма — иначе система висит минутами на мёртвом
        # OCR/LLM-эндпоинте, ничего не печатая. Недоступен OCR → сканы не распознаём (не
        # виснем); недоступен LLM → ветку Б пропускаем (хвосты/досье/веб уже готовы выше).
        from factory.config import OCR_ENABLED
        print("проверка доступности сервисов:")
        llm = Yandex(temperature=0.0)
        llm_ok = llm.probe()
        print(f"  LLM (Yandex):        {'доступен' if llm_ok else 'недоступен'}")
        ocr_client = None
        if OCR_ENABLED:
            from factory.ocr import YandexOCR
            _o = YandexOCR()
            if _o.ready and _o.probe():
                ocr_client = _o; print("  OCR (Yandex Vision): доступен")
            else:
                print("  OCR (Yandex Vision): недоступен — сканы/картинки не распознаём")
        else:
            print("  OCR (Yandex Vision): выключен (FACTORY_OCR=0)")

        if not llm_ok:
            print("\nLLM недоступен — ветка Б (извлечение из литературы) пропущена. "
                  "Детерминированные хвосты, досье OpenAlex и веб-практики уже готовы.")
        else:
            print("\nприём материалов (ветка Б)…")
            chunks = split(ingest(others, ocr=ocr_client, log=lambda m: print("  " + m)))
            prose = [c for c in chunks if c.kind == "prose" and len(c.text) >= MIN_PROSE_CHARS]
            n_state = sum(1 for c in prose if c.role == "state")
            print(f"текстовых фрагментов: {len(prose)} "
                  f"(состояние фабрики: {n_state}, справочное: {len(prose) - n_state})")

            # запрос к литературе обогащаем диагнозом ветки А (если он был)
            extra = _diagnosis_query_terms(all_hyps)
            query = f"{args.kpi} {extra}".strip() if extra else args.kpi
            if extra:
                print(f"  запрос к литературе обогащён диагнозом ветки А: «{extra}»")

            cache = None if args.no_cache else args.cache
            os.makedirs(OUTPUTS_DIR, exist_ok=True)
            rels = extract_relations(chunks, llm=llm, max_chunks=args.max_chunks,
                                     query=query, cache_path=cache, log=lambda m: print("  " + m))
            # свежие связи корпуса → подкрепить карточки ветки А цитатами литературы (с
            # локатором до страницы) и пересобрать их HTML: при прогоне «с нуля» кэша ещё
            # не было, когда ветка А рисовала отчёты (см. litsupport.py товарища)
            if rels and fabric_results:
                from factory.litsupport import enrich as lit_enrich
                from factory.report import render
                for p, res, out in fabric_results:
                    n = lit_enrich(res["hypotheses"], rels)
                    if n:
                        open(out, "w", encoding="utf-8").write(
                            render(p, res["graph"].to_layered(), res["hypotheses"],
                                   kpi=args.kpi, tech=res.get("tech"),
                                   analysis=res.get("analysis"), runinfo=runinfo))
                        print(f"  {p.fabric}: {n} карточек подкреплены цитатами корпуса "
                              f"(HTML пересобран)")
            kg = RelationGraph(rels)
            print(f"канонический граф: {kg.stats()}")
            found = discover(kg, kpi=query, limit=8)
            print(f"\nнайдено гипотез-разрывов: {len(found)}")
            for i, d in enumerate(found, 1):
                tag = "состояние фабрики" if d.role == "state" else "справочное"
                print(f"  {i}. novelty={d.novelty} [{tag}] {d.statement_if}")
            # HTML-отчёт ветки Б (report_kb) — визуальный артефакт с графом; для кейсов без
            # структурных данных (металлургия: схема+описание+промпт) это ЕДИНСТВЕННЫЙ результат
            from factory.report_kb import render_kb
            stats = kg.stats()
            tech = {"фрагментов": len(prose), "связей в кэше": len(rels),
                    "узлов графа": stats["nodes"], "рёбер": stats["edges"],
                    "кэш": cache or "выкл", "запрос к литературе": query}
            out_kb = os.path.join(OUTPUTS_DIR, "литература_гипотезы.html")
            open(out_kb, "w", encoding="utf-8").write(
                render_kb(kg.to_layered(max_nodes=24), found, kpi=args.kpi, tech=tech))
            reports.append(out_kb)
            print(f"  HTML-отчёт ветки Б: {out_kb}")

    # --- глоссарий рядом с отчётами (ссылка «как читать» в каждом отчёте ведёт сюда) ---
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    from factory.glossary import write as write_glossary
    write_glossary(OUTPUTS_DIR)

    # --- контекст прогона: какие материалы/источники использованы и что сгенерировано
    # (пути сохранены — по ним можно открывать исходники на нужном месте) ---
    import json
    from factory.client import TELEMETRY
    ctx = {"kpi": args.kpi, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
           "enrichments": [k for k, v in runinfo.items() if v],
           "tailings_used": [os.path.abspath(t) for t in tailings],
           "knowledge_used": [os.path.abspath(o) for o in others],
           "reports": [os.path.abspath(r) for r in reports],
           "glossary": os.path.abspath(os.path.join(OUTPUTS_DIR, "glossary.html"))}
    json.dump(ctx, open(os.path.join(OUTPUTS_DIR, "run_context.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # --- метрики прогона (бизнес+dev): вызовы/ретраи/задержки/токены по источникам ---
    snap = TELEMETRY.snapshot()
    if snap["total"]["calls"]:
        mpath = TELEMETRY.dump(os.path.join(OUTPUTS_DIR, "run_metrics.json"))
        t = snap["total"]
        print(f"\nметрики прогона: {t['calls']} внешних вызовов, {t['retries']} ретраев, "
              f"{t['errors']} ошибок, токенов LLM {t['tokens_in']}→{t['tokens_out']}, "
              f"{snap['wall_seconds']} c  [{mpath}]")

    print(f"\nготово: {len(reports)} отчётов + глоссарий + контекст в {OUTPUTS_DIR}/")


if __name__ == "__main__":
    main()
