# -*- coding: utf-8 -*-
"""Сводный евал: ветка А (golden-coverage хвостов) + судья по ВСЕМ гипотезам.

Ветка А (детерминированно, без LLM): по каждой фабрике строит гипотезы из Хвосты*.xlsx
и сверяет с эталоном Гипотезы*.docx по семействам вмешательства → family-coverage.

Судья (нужен ключ Yandex): оценивает и ветку А, и ветку Б по единой рубрике. Бенчмарк
здесь НЕ делает свою LLM-экстракцию литературы — ветку Б наполняет ТОЛЬКО flex.py;
бенчмарк лишь читает уже готовый кэш графа и оценивает то, что там есть (см. judge.py).
Так избегаем рассинхрона: разные пути/лимиты в разных командах раньше приводили к
несовпадению отпечатка кэша и повторной незапланированной экстракции.

Запуск:  python -m factory.flex materials --kpi "..."   # СНАЧАЛА: наполнить кэш графа + конфиг
         python -m factory.benchmark                     # KPI подхватится из конфига flex
         python -m factory.benchmark --kpi "..."          # или явно (побеждает конфиг)
         python -m factory.benchmark --no-judge           # только ветка А (KPI не нужен)
"""
from __future__ import annotations

import argparse
import glob
import os

from factory.config import DEFAULT_CACHE
from factory.evaluate import _GOLDEN_TEST_KPI, family_of, golden_lines
from factory.pipeline import HypothesisFactory
from factory.runconfig import resolve_kpi


def _find_pair(fabric_dir):
    xlsx = glob.glob(os.path.join(fabric_dir, "Хвосты*.xlsx"))
    docx = glob.glob(os.path.join(fabric_dir, "Гипотезы*.docx"))
    return (xlsx[0] if xlsx else None, docx[0] if docx else None)


def eval_fabric(xlsx, docx):
    # golden-coverage — регрессионный тест диагностики, не бизнес-вопрос пользователя;
    # видимый тестовый KPI (см. evaluate.py), не связан с --kpi ниже (тот — для судьи)
    hyps = HypothesisFactory(xlsx, kpi=_GOLDEN_TEST_KPI).run()["hypotheses"]
    our = {family_of(f"{h.family} {h.intervention} {h.statement_if}") for h in hyps}
    our |= {family_of(a) for h in hyps for a in h.alternatives}
    our -= {None}
    golden = golden_lines(docx)
    covered = [(g, family_of(g)) for g in golden]
    hit = sum(1 for _, f in covered if f in our)
    return {"n_hyp": len(hyps), "our": our, "golden": covered,
            "hit": hit, "total": len(golden)}


def _run_judge(fabrics_root, cache_path, kpi, kpi_source):
    """Судья по ВСЕМ гипотезам системы (ветка А хвосты + ветка Б из кэша flex).
    Возвращает res (items/aggregate/by_branch) или None."""
    from factory.judge import judge_everything
    log = lambda m: print("  " + m)
    print("\n" + "=" * 78)
    print("LLM-AS-JUDGE · ОЦЕНКА ВСЕХ ГИПОТЕЗ (ХВОСТЫ + ЛИТЕРАТУРА ИЗ КЭША)")
    print("=" * 78)
    print(f"KPI судьи: «{kpi}»  [источник: {kpi_source}]")
    res = judge_everything(fabrics_dir=fabrics_root, cache_path=cache_path, kpi=kpi, log=log)
    if res is None:
        print("\n(судья пропущен: нет ключа Yandex в .env либо гипотез не нашлось)")
        return None
    print(f"гипотез к оценке: {len(res['records'])}")
    a = res["aggregate"]
    if a.get("judged"):
        print(f"\nСУДЕЙСКИЙ БАЛЛ (все гипотезы): {a['overall']}/5 "
              f"(оценено {a['judged']}/{a['n']})")
        for label, agg in res["by_branch"].items():
            if agg.get("judged"):
                print(f"  {label}: {agg['overall']}/5 (n={agg['judged']})")
    return res


def main():
    ap = argparse.ArgumentParser(description="Сводный евал: ветка А (golden) + судья")
    ap.add_argument("root", nargs="?", default="materials/fabrics", help="папка с фабриками")
    ap.add_argument("--cache", default=DEFAULT_CACHE,
                    help="кэш графа, наполненный 'python -m factory.flex ...' — ветка Б")
    ap.add_argument("--kpi", default="", help="KPI для судьи; если не задан — берётся из "
                    "конфига последнего flex-запуска. Обязателен, если судья запускается "
                    "(т.е. без --no-judge) и конфига нет")
    ap.add_argument("--no-judge", action="store_true", help="только ветка А (--kpi не нужен)")
    args = ap.parse_args()

    # KPI судьи: явный --kpi побеждает, иначе — конфиг последнего flex-запуска.
    # Источник ВСЕГДА объявляется, чтобы не было «магии» (см. runconfig.resolve_kpi).
    judge_kpi, kpi_source = ("", "")
    if not args.no_judge:
        judge_kpi, kpi_source = resolve_kpi(args.kpi)
        if not judge_kpi:
            ap.error("--kpi для судьи не задан и не найден в конфиге последнего запуска "
                     f"({kpi_source}). Запустите сначала 'python -m factory.flex ... --kpi "
                     "\"...\"', либо передайте --kpi здесь, либо --no-judge без судьи.")
    dirs = sorted(d for d in glob.glob(os.path.join(args.root, "*")) if os.path.isdir(d))

    print("=" * 78)
    print("ВЕТКА А · GOLDEN-БЕНЧМАРК ПО ФАБРИКАМ (детерминированно, без LLM)")
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

    print("\n" + "-" * 78)
    total_cov = agg_hit / agg_total if agg_total else 0
    print(f"ВЕТКА А: {agg_hit}/{agg_total} эталонных гипотез = {total_cov:.0%} family-coverage "
          "(из данных, не подсказано)")

    judge_res = None
    if not args.no_judge:
        judge_res = _run_judge(args.root, args.cache, judge_kpi, kpi_source)

    print("\n" + "=" * 78)
    print("СВОДНАЯ ОЦЕНКА")
    print(f"  Ветка А (хвосты → golden):     {total_cov:.0%} family-coverage ({agg_hit}/{agg_total})")
    ja = judge_res["aggregate"] if judge_res else None
    if ja and ja.get("judged"):
        print(f"  Судья (все гипотезы, вне ранжирования): {ja['overall']}/5 "
              f"(оценено {ja['judged']}/{ja['n']})")
        for label, agg in judge_res["by_branch"].items():
            if agg.get("judged"):
                print(f"    · {label}: {agg['overall']}/5")
    else:
        print("  Судья: не оценивал (нет ключа/гипотез или --no-judge)")
    print("=" * 78)


if __name__ == "__main__":
    main()
