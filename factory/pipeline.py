# -*- coding: utf-8 -*-
"""Оркестратор фабрики гипотез. Собирает модули в единый пайплайн (OOP).

Поток: ЧТЕНИЕ (reader) → ГРАФ (knowledge) → ГЕНЕРАЦИЯ+МЕТРИКИ (generator/metrics,
детерминированно) → [опц. LLM-полировка текста] → ОТЧЁТ (report).
"""
from __future__ import annotations

import time

from factory.analysis import analyze
from factory.config import OUTPUTS_DIR
from factory.generator import HypothesisGenerator
from factory.intent import parse_intent, warn_intent
from factory.knowledge import ProfileGraph
from factory.reader import TailingsReader
from factory.report import render
from factory.schema import DEFAULT_SCHEMA, ReportSchema


class HypothesisFactory:
    def __init__(self, path: str, kpi: str, polish: bool = False,
                schema: ReportSchema = DEFAULT_SCHEMA):
        if not kpi or not kpi.strip():
            raise ValueError("KPI обязателен: без него неясно, что оптимизировать. "
                             "Передайте реальную цель, напр. kpi=\"снизить потери "
                             "никеля с хвостами флотации\".")
        self.path = path
        self.kpi = kpi
        self.polish = polish
        self.schema = schema

    def run(self):
        t0 = time.perf_counter()
        intent = parse_intent(self.kpi)                     # KPI → целевой элемент + ограничения
        profile = TailingsReader(self.path, schema=self.schema).read()  # детерм. чтение по схеме
        graph = ProfileGraph(profile)                       # граф профиля потерь (ветка А)
        analysis = analyze(profile, element=intent.target_element)  # кривая раскрытия / формы
        hyps = HypothesisGenerator().generate(profile, kpi=self.kpi)  # диагноз + метрики (детерм.)

        # фидбэк эксперта (outputs/feedback.json, наполняется factory.feedback import):
        # детерминированный ре-ранк — «уже пробовали»/«неверно» опускаются, не скрываясь
        from factory.feedback import apply_feedback
        fb_applied = apply_feedback(hyps, profile.fabric)

        used_llm = "нет"
        if self.polish:
            from factory.llm import Phraser
            ph = Phraser()
            if ph.ready:
                hyps = ph.polish(hyps)
                used_llm = "да (только текст)"
        tech = {"seconds": round(time.perf_counter() - t0, 2), "llm": used_llm,
                "feedback": fb_applied, **graph.stats()}
        html = render(profile, graph.to_layered(), hyps, kpi=self.kpi, tech=tech,
                      analysis=analysis)
        return {"profile": profile, "graph": graph, "analysis": analysis, "intent": intent,
                "hypotheses": hyps, "html": html, "tech": tech}


def main():
    import argparse
    import json
    import os

    ap = argparse.ArgumentParser(description="Фабрика гипотез по хвостам обогащения")
    ap.add_argument("report", help="путь к Excel-отчёту (Хвосты *.xlsx)")
    ap.add_argument("--kpi", required=True, help="обязателен: целевая метрика/проблема, "
                    "напр. \"снизить потери никеля с хвостами флотации\"")
    ap.add_argument("--polish", action="store_true", help="LLM-полировка текста (Yandex)")
    ap.add_argument("--schema", default="", help="путь к JSON-схеме формата отчёта "
                    "(по умолчанию — известный формат; см. schema.py/schema_bootstrap.py)")
    ap.add_argument("--out", default="", help="куда сохранить HTML (по умолчанию рядом)")
    ap.add_argument("--export", default="", metavar="ФОРМАТЫ",
                    help="дополнительно выгрузить гипотезы: all либо через запятую из "
                    "{json,csv,tasks,pdf,docx} (детерминированно, без LLM; "
                    "см. factory/export.py)")
    args = ap.parse_args()

    if not os.path.exists(args.report):
        ap.error(f"файл отчёта не найден: {args.report}")

    schema = DEFAULT_SCHEMA
    if args.schema:
        from factory.schema import load_schema
        schema = load_schema(args.schema)

    res = HypothesisFactory(args.report, kpi=args.kpi, polish=args.polish, schema=schema).run()
    p, hyps, tech = res["profile"], res["hypotheses"], res["tech"]

    print("=" * 74)
    print(f"ФАБРИКА ГИПОТЕЗ · {p.fabric}  ({p.source})")
    print(f"детерминированно за {tech['seconds']} c · граф {tech['nodes']} узлов / "
          f"{tech['edges']} рёбер · LLM: {tech['llm']}")
    print("=" * 74)
    warn_intent(res["intent"], args.kpi)
    if tech.get("feedback"):
        print(f"⚑ применён фидбэк эксперта к {tech['feedback']} гипотезам — приоритеты "
              f"скорректированы (база: feedback.json, см. factory.feedback)")
    if p.warnings:
        print("⚠ ВАЛИДАЦИЯ (парс мог сбиться):")
        for w in p.warnings:
            print(f"   · {w}")
        print()
    total_ni = round(sum(h.metrics["rec_tonnes"].get("Ni", 0) for h in hyps), 1)
    total_cu = round(sum(h.metrics["rec_tonnes"].get("Cu", 0) for h in hyps), 1)
    target = hyps[0].target_element if hyps else "?"
    print(f"извлекаемого металла в хвостах (факт): {total_ni} т Ni + {total_cu} т Cu "
          f"| целевой элемент по KPI: {target} | гипотез: {len(hyps)}")
    print("оценка безразмерна: impact — масштаб потери, addressability — излечимость, "
          "clarity — ясность механизма\n")
    for h in hyps:
        m = h.metrics
        warn = f"  ⚠ нарушает: {', '.join(h.violates_constraints)}" if h.violates_constraints else ""
        print(f"#{h.rank}  impact={round(m['impact']*100)}%  приоритет={m['priority']}  "
              f"[{h.family}]  класс {h.size_class}{warn}")
        print(f"     ЕСЛИ  {h.statement_if}")
        print(f"     ТО    {h.statement_then}")
        print(f"     ПЧ    {h.statement_because}")
        print(f"     ЭКСПЕРИМЕНТ  {h.experiment}")
        print(f"     приоритет={m['priority']} реализуемость={m['feasibility']} "
              f"достоверность={m['confidence']} | ячейки: "
              f"{', '.join(e['cell'] for e in h.evidence)}")
        print(f"     источники: {'; '.join(h.sources)}")
        print()

    if args.out:
        out = args.out
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)  # --out в новую папку — не падать
    else:
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        out = os.path.join(OUTPUTS_DIR, f"{p.fabric}_гипотезы.html")
    open(out, "w", encoding="utf-8").write(res["html"])
    from factory.glossary import write as write_glossary
    write_glossary(os.path.dirname(out) or ".")   # glossary.html рядом (ссылка из отчёта)
    print(f"HTML-отчёт с графом: {out}  (+ glossary.html рядом)")

    if args.export:
        from factory.export import export_all
        print("\nЭКСПОРТ (те же гипотезы, что в HTML — единый слой serialize):")
        export_all(hyps, profile=p, kpi=args.kpi, formats=args.export,
                   out_dir=os.path.dirname(out) or OUTPUTS_DIR, log=print)


if __name__ == "__main__":
    main()
