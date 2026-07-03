# -*- coding: utf-8 -*-
"""Сводный прогон по ВСЕМ фабрикам как один golden-бенчмарк. ДЕТЕРМИНИРОВАННО.

Для каждой фабрики: строит гипотезы из Хвосты*.xlsx и сверяет с эталоном Гипотезы*.docx
по семействам вмешательства. Печатает таблицу по фабрикам + агрегат по всем эталонам.

Запуск:  python -m factory.benchmark            # по всем materials/fabrics/*
         python -m factory.benchmark <dir>      # своя папка с фабриками
"""
from __future__ import annotations

import glob
import os
import sys

from factory.evaluate import family_of, golden_lines
from factory.pipeline import HypothesisFactory


def _find_pair(fabric_dir):
    xlsx = glob.glob(os.path.join(fabric_dir, "Хвосты*.xlsx"))
    docx = glob.glob(os.path.join(fabric_dir, "Гипотезы*.docx"))
    return (xlsx[0] if xlsx else None, docx[0] if docx else None)


def eval_fabric(xlsx, docx):
    hyps = HypothesisFactory(xlsx).run()["hypotheses"]
    our = {family_of(f"{h.family} {h.intervention} {h.statement_if}") for h in hyps}
    our |= {family_of(a) for h in hyps for a in h.alternatives}
    our -= {None}
    golden = golden_lines(docx)
    covered = [(g, family_of(g)) for g in golden]
    hit = sum(1 for _, f in covered if f in our)
    return {"n_hyp": len(hyps), "our": our, "golden": covered,
            "hit": hit, "total": len(golden)}


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "materials/fabrics"
    dirs = sorted(d for d in glob.glob(os.path.join(root, "*")) if os.path.isdir(d))

    print("=" * 78)
    print("GOLDEN-БЕНЧМАРК ПО ВСЕМ ФАБРИКАМ (детерминированно, без LLM)")
    print("=" * 78)
    agg_hit = agg_total = 0
    rows = []
    for d in dirs:
        xlsx, docx = _find_pair(d)
        if not (xlsx and docx):
            continue
        r = eval_fabric(xlsx, docx)
        agg_hit += r["hit"]; agg_total += r["total"]
        rows.append((os.path.basename(d), r))
        cov = r["hit"] / r["total"] if r["total"] else 0
        print(f"\n■ {os.path.basename(d):<10} гипотез: {r['n_hyp']} | "
              f"покрытие эталона: {r['hit']}/{r['total']} = {cov:.0%}")
        print(f"    наши семейства: {sorted(r['our'])}")
        for g, f in r["golden"]:
            mark = "✓" if f in r["our"] else "·"
            print(f"    {mark} [{f or 'н/распознано':<20}] {g[:44]}")

    print("\n" + "=" * 78)
    total_cov = agg_hit / agg_total if agg_total else 0
    print(f"ИТОГО ПО ВСЕМ ФАБРИКАМ: {agg_hit}/{agg_total} эталонных гипотез = "
          f"{total_cov:.0%} family-coverage")
    print("(вмешательства выведены из данных детерминированно, не подсказаны модели)")
    print("=" * 78)


if __name__ == "__main__":
    main()
