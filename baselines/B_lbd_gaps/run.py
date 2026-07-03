#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ПОДСТРАХОВОЧНЫЙ бейзлайн · LBD / разрывы Свонсона по АВТО-графу (детерминированный).

«Взгляд с другой стороны» на тот же автоматически извлечённый граф знаний:
не LLM-креатив, а ТОПОЛОГИЯ. Если в графе есть A→B и B→C, но прямой связи A→C нет —
это кандидат-гипотеза (скрытая связь, которую никто не проверял). Полностью
детерминирован и интерпретируем: тот же граф → тот же список.

Граф берётся из кэша основного бейзлайна (`A_grounded_generation/kb_cache.json`) —
то есть факты те же, извлечены автоматически с цитатным гейтом. Руками ничего не пишется.

Запуск:
    uv run python run.py                       # берёт кэш графа основного бейзлайна
    uv run python run.py --kb <путь к kb_cache.json>

Зависимости: только стандартная библиотека (граф уже извлечён и лежит в кэше).
"""
from __future__ import annotations

import argparse
import json
import os
import re

_n = [0]
def step(msg):
    _n[0] += 1; print(f"\n[{_n[0]}] ── {msg}")
def sub(msg):
    print(f"       {msg}")


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def tokens(s):
    return set(re.findall(r"[а-яёa-z]{4,}", norm(s)))


def similar(a, b):
    """Нечёткое совпадение сущностей: доля общих значимых токенов."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def find_gaps(facts, thr=0.5):
    """A→B и B→C есть, прямой A→C нет → кандидат (нечёткий матч сущностей)."""
    edges = [(f["subject"], f["object"], f) for f in facts]
    gaps = []
    for a, b, f1 in edges:
        for b2, c, f2 in edges:
            if similar(b, b2) < thr:        # B ≈ B2 (звено стыкуется)
                continue
            if similar(a, c) >= thr:         # A и C — по сути одно, не разрыв
                continue
            if any(similar(a, s) >= thr and similar(c, o) >= thr for s, o, _ in edges):
                continue                     # прямая связь A→C уже есть
            gaps.append((a, b, c, f1, f2))
    # дедуп по (нормализованные A,C)
    seen, uniq = set(), []
    for g in gaps:
        key = (norm(g[0]), norm(g[2]))
        if key in seen:
            continue
        seen.add(key); uniq.append(g)
    return uniq


def main():
    ap = argparse.ArgumentParser()
    default_kb = os.path.join(os.path.dirname(__file__), "..",
                              "A_grounded_generation", "kb_cache.json")
    ap.add_argument("--kb", default=default_kb)
    ap.add_argument("--thr", type=float, default=0.5)
    args = ap.parse_args()

    print("=" * 78)
    print("LBD / РАЗРЫВЫ СВОНСОНА по авто-графу (детерминированно)")
    print("=" * 78)

    if not os.path.exists(args.kb):
        print(f"Нет кэша графа: {args.kb}\nСначала запустите основной бейзлайн "
              "(A_grounded_generation/run.py) — он извлечёт граф автоматически.")
        return
    kb = json.load(open(args.kb, encoding="utf-8"))
    facts = kb["facts"]

    step(f"Загружен авто-граф: {len(facts)} связей (извлечены LLM с цитатным гейтом)")
    for f in facts:
        sub(f"({f['subject']}) →{f['sign']}→ ({f['object']})  [{f['locator']}]")

    step(f"Ищу разрывы A→B→C без прямого A→C (нечёткий матч, порог {args.thr})")
    gaps = find_gaps(facts, thr=args.thr)
    sub(f"найдено кандидатов: {len(gaps)}")
    if not gaps:
        sub("на текущем графе цепочек не найдено — граф разрежен.")
        sub("увеличьте охват извлечения: A_grounded_generation/run.py --max-chunks 20")

    step("КАНДИДАТЫ-ГИПОТЕЗЫ (скрытые связи):")
    for i, (a, b, c, f1, f2) in enumerate(gaps, 1):
        print(f"\n   #{i}  скрытая связь: «{a}» → «{c}»")
        print(f"       ЕСЛИ:  воздействовать на «{c}» через «{a}»")
        print(f"       ПОТОМУ ЧТО: «{a}»→«{b}» и «{b}»→«{c}», но прямой связи "
              f"«{a}»→«{c}» в корпусе нет (разрыв Свонсона)")
        print(f"       ↳ [{f1['locator']}] «{f1['quote'][:80]}»")
        print(f"       ↳ [{f2['locator']}] «{f2['quote'][:80]}»")

    print("\n" + "=" * 78)
    print("Тот же авто-граф, что и у основного бейзлайна — другой метод генерации.")
    print("Детерминированно и интерпретируемо: топология вместо LLM-креатива.")
    print("=" * 78)


if __name__ == "__main__":
    main()
