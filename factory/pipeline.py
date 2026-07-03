# -*- coding: utf-8 -*-
"""Оркестратор фабрики гипотез. Собирает модули в единый пайплайн (OOP).

Поток: ЧТЕНИЕ (reader) → ГРАФ (knowledge) → ГЕНЕРАЦИЯ+МЕТРИКИ (generator/metrics,
детерминированно) → [опц. LLM-полировка текста] → ОТЧЁТ (report).
"""
from __future__ import annotations

import time

from factory.analysis import analyze
from factory.config import DEFAULT_KPI, OUTPUTS_DIR
from factory.generator import HypothesisGenerator
from factory.knowledge import KnowledgeGraph
from factory.reader import TailingsReader
from factory.report import render


class HypothesisFactory:
    def __init__(self, path: str, kpi: str = "", polish: bool = False):
        self.path = path
        self.kpi = kpi or DEFAULT_KPI
        self.polish = polish

    def run(self):
        t0 = time.perf_counter()
        profile = TailingsReader(self.path).read()          # детерминированное чтение
        graph = KnowledgeGraph(profile)                     # граф знаний
        analysis = analyze(profile)                         # кривая раскрытия / trade-off / формы
        hyps = HypothesisGenerator().generate(profile)      # диагноз + метрики (детерм.)

        used_llm = "нет"
        if self.polish:
            from factory.llm import Phraser
            ph = Phraser()
            if ph.ready:
                hyps = ph.polish(hyps)
                used_llm = "да (только текст)"
        tech = {"seconds": round(time.perf_counter() - t0, 2), "llm": used_llm,
                **graph.stats()}
        html = render(profile, graph.to_layered(), hyps, kpi=self.kpi, tech=tech,
                      analysis=analysis)
        return {"profile": profile, "graph": graph, "analysis": analysis,
                "hypotheses": hyps, "html": html, "tech": tech}


def main():
    import argparse
    import json
    import os

    ap = argparse.ArgumentParser(description="Фабрика гипотез по хвостам обогащения")
    ap.add_argument("report", help="путь к Excel-отчёту (Хвосты *.xlsx)")
    ap.add_argument("--kpi", default="")
    ap.add_argument("--polish", action="store_true", help="LLM-полировка текста (Yandex)")
    ap.add_argument("--out", default="", help="куда сохранить HTML (по умолчанию рядом)")
    args = ap.parse_args()

    res = HypothesisFactory(args.report, kpi=args.kpi, polish=args.polish).run()
    p, hyps, tech = res["profile"], res["hypotheses"], res["tech"]

    print("=" * 74)
    print(f"ФАБРИКА ГИПОТЕЗ · {p.fabric}  ({p.source})")
    print(f"детерминированно за {tech['seconds']} c · граф {tech['nodes']} узлов / "
          f"{tech['edges']} рёбер · LLM: {tech['llm']}")
    print("=" * 74)
    if p.warnings:
        print("⚠ ВАЛИДАЦИЯ (парс мог сбиться):")
        for w in p.warnings:
            print(f"   · {w}")
        print()
    total_ni = round(sum(h.metrics["rec_tonnes"].get("Ni", 0) for h in hyps), 1)
    total_cu = round(sum(h.metrics["rec_tonnes"].get("Cu", 0) for h in hyps), 1)
    print(f"извлекаемого металла в хвостах (факт): {total_ni} т Ni + {total_cu} т Cu "
          f"| гипотез: {len(hyps)}")
    print("оценка безразмерна: impact — масштаб потери, addressability — излечимость, "
          "clarity — ясность механизма\n")
    for h in hyps:
        m = h.metrics
        print(f"#{h.rank}  impact={round(m['impact']*100)}%  приоритет={m['priority']}  "
              f"[{h.family}]  класс {h.size_class}")
        print(f"     ЕСЛИ  {h.statement_if}")
        print(f"     ТО    {h.statement_then}")
        print(f"     ПЧ    {h.statement_because}")
        print(f"     приоритет={m['priority']} реализуемость={m['feasibility']} "
              f"достоверность={m['confidence']} | ячейки: "
              f"{', '.join(e['cell'] for e in h.evidence)}")
        print()

    if args.out:
        out = args.out
    else:
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        out = os.path.join(OUTPUTS_DIR, f"{p.fabric}_гипотезы.html")
    open(out, "w", encoding="utf-8").write(res["html"])
    from factory.glossary import write as write_glossary
    write_glossary(os.path.dirname(out) or ".")   # glossary.html рядом (ссылка из отчёта)
    print(f"HTML-отчёт с графом: {out}  (+ glossary.html рядом)")


if __name__ == "__main__":
    main()
