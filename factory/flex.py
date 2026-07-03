# -*- coding: utf-8 -*-
"""Гибкий приём: загрузи ЧТО УГОДНО (папка/файлы) → система разбирается сама.

Диспетчер по типу данных:
  • отчёт по хвостам (xlsx со структурой) → ДЕТЕРМИНИРОВАННАЯ диагностика (factory core);
  • прочий текст (PDF/DOCX/TXT/патенты/статьи) → LLM-извлечение связей (цитатный гейт,
    кэш) → канонический граф → разрывы Свонсона (детерминированно поверх кэша).

Так закрывается требование ТЗ «гибкость входных данных»: детерминизм — в рассуждении,
LLM — только в понимании неструктурированного текста, с заземлением до цитаты/страницы.

Запуск:
    uv run python -m factory.flex materials --kpi "снизить потери никеля с хвостами"
    uv run python -m factory.flex materials/reference/books --kpi "повысить извлечение Ni"
"""
from __future__ import annotations

import argparse
import os

from factory.config import DEFAULT_CACHE, DEFAULT_KPI, MIN_PROSE_CHARS, OUTPUTS_DIR
from factory.ingest import ingest, split


def _is_tailings(path):
    """Отчёт по хвостам? Пробуем специализированный ридер — есть ли классы крупности."""
    if not path.lower().endswith(".xlsx"):
        return False
    try:
        from factory.reader import TailingsReader
        return len(TailingsReader(path).read().classes) >= 3
    except Exception:  # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser(description="Гибкая фабрика гипотез (загрузи что угодно)")
    ap.add_argument("paths", nargs="+", help="файлы или папки с материалами")
    ap.add_argument("--kpi", default=DEFAULT_KPI)
    ap.add_argument("--max-chunks", type=int, default=14)
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    print("=" * 74)
    print("ГИБКИЙ ПРИЁМ МАТЕРИАЛОВ")
    print(f"KPI: {args.kpi}")
    print("=" * 74)

    # --- собрать все файлы, отделить отчёты по хвостам от прочего текста ---
    all_files = []
    for p in args.paths:
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
    print(f"\nотчётов по хвостам: {len(tailings)} | прочих материалов (знание): {len(others)}")

    # --- ветка 1: детерминированная диагностика хвостов ---
    if tailings:
        from factory.pipeline import HypothesisFactory
        print("\n" + "─" * 74)
        print("ДЕТЕРМИНИРОВАННАЯ ДИАГНОСТИКА ХВОСТОВ (без LLM)")
        print("─" * 74)
        for t in tailings:
            res = HypothesisFactory(t, kpi=args.kpi).run()
            p, hyps = res["profile"], res["hypotheses"]
            os.makedirs(OUTPUTS_DIR, exist_ok=True)
            out = os.path.join(OUTPUTS_DIR, f"{p.fabric}_гипотезы.html")
            open(out, "w", encoding="utf-8").write(res["html"])
            top = hyps[0] if hyps else None
            print(f"  ■ {p.fabric}: {len(hyps)} гипотез; топ — {top.statement_if if top else '—'}")
            print(f"    → {out}")

    # --- ветка 2: извлечение из текста → граф → открытие ---
    if others:
        from factory.discover import discover
        from factory.extract import extract_relations
        from factory.kgraph import KnowledgeGraph
        from factory.llm import Yandex
        print("\n" + "─" * 74)
        print("ИЗВЛЕЧЕНИЕ ИЗ ТЕКСТА → ГРАФ → РАЗРЫВЫ СВОНСОНА")
        print("─" * 74)
        chunks = split(ingest(others))
        prose = [c for c in chunks if c.kind == "prose" and len(c.text) >= MIN_PROSE_CHARS]
        print(f"текстовых фрагментов: {len(prose)}")
        llm = Yandex(temperature=0.0)
        if not llm.ready:
            print("⚠ нет ключа Yandex (.env) — извлечение из текста недоступно. "
                  "Отчёты по хвостам работают без ключа.")
            return
        cache = None if args.no_cache else args.cache
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        rels = extract_relations(chunks, llm=llm, max_chunks=args.max_chunks,
                                 query=args.kpi, cache_path=cache, log=lambda m: print("  " + m))
        kg = KnowledgeGraph(rels)
        print(f"канонический граф: {kg.stats()}")
        found = discover(kg, kpi=args.kpi, limit=8)
        print(f"\nнайдено гипотез-разрывов: {len(found)}")
        for i, d in enumerate(found, 1):
            print(f"\n  #{i} score={d.score} novelty={d.novelty}")
            print(f"     ЕСЛИ: {d.statement_if}")
            print(f"     ПЧ:   {d.statement_because}")
            print(f"     источники: {', '.join(s for s in d.sources if s)}")

    print("\n" + "=" * 74)
    print("Детерминизм — в рассуждении; LLM — только в понимании текста (с цитатным гейтом).")
    print("=" * 74)


if __name__ == "__main__":
    main()
