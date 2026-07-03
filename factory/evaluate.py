# -*- coding: utf-8 -*-
"""Оценка против эталона организаторов (Гипотезы*.docx). ДЕТЕРМИНИРОВАННО.

Сравнение по СЕМЕЙСТВУ вмешательства (устойчиво к формулировке), без LLM и эмбеддингов.
Показывает, какие эталонные направления покрыты нашими гипотезами.

Запуск:  python -m factory.evaluate data/Хвосты\\ ТОФ_2.xlsx data/Гипотезы\\ ТОФ.docx
"""
from __future__ import annotations

import html
import os
import re
import sys
import zipfile

from factory.pipeline import HypothesisFactory

FAMILIES = {
    "измельчение/раскрытие": ["футеровк", "мельниц", "измельч", "доизмельч", "раскрыт",
                              "гранулометри", "дроб", "шар"],
    "классификация": ["классифик", "гидроцикл", "циклон", "насадк", "классификатор",
                      "возвратн", "контрольн"],
    "грохочение": ["грохот", "грохочен", "сито", "ситов"],
    "флотация-схема": ["флотац", "контактн", "чан", "перечист", "фронт",
                       "возврат в голов", "агитац", "плотност"],
    "реагенты": ["реагент", "собират", "ксантоген", "депрессор", "кмц", "подавл",
                 "купорос"],
}


def family_of(text: str):
    low = " " + text.lower()
    best, score = None, 0
    for fam, kws in FAMILIES.items():
        s = sum(low.count(k) for k in kws)
        if s > score:
            best, score = fam, s
    return best


def golden_lines(path: str):
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8", "ignore")
    text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml)))
    return [l.strip(" .0123456789") for l in text.splitlines()
            if len(l.strip()) > 8 and "мозгов" not in l.lower()]


def main():
    if len(sys.argv) < 3:
        print("usage: python -m factory.evaluate <отчёт.xlsx> <Гипотезы.docx>"); return
    report, golden_path = sys.argv[1], sys.argv[2]

    hyps = HypothesisFactory(report).run()["hypotheses"]
    our_fams = {family_of(f"{h.family} {h.intervention} {h.statement_if}") for h in hyps}
    our_fams |= {family_of(a) for h in hyps for a in h.alternatives}
    our_fams -= {None}

    golden = golden_lines(golden_path)
    gfams = [family_of(g) for g in golden]

    print("=" * 74)
    print(f"ОЦЕНКА против эталона · {os.path.basename(golden_path)}")
    print("=" * 74)
    print(f"наши семейства вмешательств: {sorted(our_fams)}\n")
    hit = 0
    for g, f in zip(golden, gfams):
        mark = "✓" if f in our_fams else "·"
        if f in our_fams:
            hit += 1
        print(f"  {mark} [{f or 'не распознано':<22}] {g[:44]}")
    cov = hit / len(golden) if golden else 0
    print(f"\nFAMILY-COVERAGE = {hit}/{len(golden)} = {cov:.0%}  (детерминированно, "
          f"без LLM; вмешательства выведены из данных, а не подсказаны)")
    print("=" * 74)


if __name__ == "__main__":
    main()
