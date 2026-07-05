from __future__ import annotations

import argparse
import glob
import os

from factory.config import DEFAULT_CACHE
from factory.evals.evaluate import _GOLDEN_TEST_KPI, family_of, golden_lines
from factory.pipeline import HypothesisFactory
from factory.runconfig import resolve_kpi


def _find_pair(fabric_dir):
    xlsx = glob.glob(os.path.join(fabric_dir, "Хвосты*.xlsx"))
    docx = glob.glob(os.path.join(fabric_dir, "Гипотезы*.docx"))
    return (xlsx[0] if xlsx else None, docx[0] if docx else None)

def eval_fabric(xlsx, docx):

    hyps = HypothesisFactory(xlsx, kpi=_GOLDEN_TEST_KPI).run()["hypotheses"]
    our = {family_of(f"{h.family} {h.intervention} {h.statement_if}") for h in hyps}
    our |= {family_of(a) for h in hyps for a in h.alternatives}
    our -= {None}
    golden = golden_lines(docx)
    covered = [(g, family_of(g)) for g in golden]
    golden_fams = {f for _, f in covered} - {None}
    hit = sum(1 for _, f in covered if f in our)

    precision_hits = sum(1 for f in our if f in golden_fams)
    grounded = sum(1 for h in hyps if getattr(h, "evidence", None))
    return {"n_hyp": len(hyps), "our": our, "golden": covered,
            "hit": hit, "total": len(golden),
            "precision_hit": precision_hits, "precision_den": len(our),
            "grounded": grounded}

def _run_judge(fabrics_root, cache_path, kpi, kpi_source):
    from factory.evals.judge import judge_everything
    from factory.ext.llm import Yandex
    log = lambda m: print("  " + m)
    print("\nLLM-as-judge — оценка всех гипотез (хвосты + литература из кэша):")

    if not Yandex().probe():
        print("  LLM (Yandex): недоступен — судья пропущен (ветка А выше уже посчитана).")
        return None
    print("  LLM (Yandex): доступен")
    print(f"  KPI судьи: «{kpi}»  [источник: {kpi_source}]")
    res = judge_everything(fabrics_dir=fabrics_root, cache_path=cache_path, kpi=kpi, log=log)
    if res is None:
        print("  судья пропущен: гипотез не нашлось.")
        return None
    print(f"  гипотез к оценке: {len(res['records'])}")
    a = res["aggregate"]
    if a.get("judged"):
        print(f"  судейский балл (все гипотезы): {a['overall']}/5 "
              f"(оценено {a['judged']}/{a['n']})")
        for label, agg in res["by_branch"].items():
            if agg.get("judged"):
                print(f"    {label}: {agg['overall']}/5 (n={agg['judged']})")
    return res

def main():
    import sys
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Сводный евал: ветка А (golden) + судья")
    ap.add_argument("root", nargs="?", default="materials/data/fabrics", help="папка с фабриками")
    ap.add_argument("--cache", default=DEFAULT_CACHE,
                    help="кэш графа, наполненный 'python -m factory.flex ...' — ветка Б")
    ap.add_argument("--kpi", default="", help="KPI для судьи; если не задан — берётся из "
                    "конфига последнего flex-запуска. Обязателен, если судья запускается "
                    "(т.е. без --no-judge) и конфига нет")
    ap.add_argument("--no-judge", action="store_true", help="только ветка А (--kpi не нужен)")
    args = ap.parse_args()

    judge_kpi, kpi_source = ("", "")
    if not args.no_judge:
        judge_kpi, kpi_source = resolve_kpi(args.kpi)
        if not judge_kpi:
            ap.error("--kpi для судьи не задан и не найден в конфиге последнего запуска "
                     f"({kpi_source}). Запустите сначала 'python -m factory.flex ... --kpi "
                     "\"...\"', либо передайте --kpi здесь, либо --no-judge без судьи.")
    dirs = sorted(d for d in glob.glob(os.path.join(args.root, "*")) if os.path.isdir(d))

    print("ветка А — golden-бенчмарк по фабрикам (детерминированно, без LLM):")
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
        prec = r["precision_hit"] / r["precision_den"] if r["precision_den"] else 0
        grnd = r["grounded"] / r["n_hyp"] if r["n_hyp"] else 0
        print(f"\n  {os.path.basename(d):<10} гипотез: {r['n_hyp']} | "
              f"recall: {r['hit']}/{r['total']} = {cov:.0%} | "
              f"precision: {r['precision_hit']}/{r['precision_den']} = {prec:.0%} | "
              f"grounding: {grnd:.0%}")
        print(f"    наши семейства: {sorted(r['our'])}")
        for g, f in r["golden"]:
            mark = "+" if f in r["our"] else "-"
            print(f"    {mark} [{f or 'н/распознано':<20}] {g[:44]}")

    print()
    total_cov = agg_hit / agg_total if agg_total else 0
    print(f"ветка А: {agg_hit}/{agg_total} эталонных гипотез = {total_cov:.0%} family-coverage "
          "(recall из данных, не подсказано)")
    print("оговорка: официальный тест-эталон — одна пара (QA), остальные фабрики держим как "
          "разведочные. Family-coverage меряет пересечение словаря семейств и завышается, "
          "если каталог широк; поэтому рядом precision (не лишнее ли) и grounding (ячейки).")

    judge_res = None
    if not args.no_judge:
        judge_res = _run_judge(args.root, args.cache, judge_kpi, kpi_source)

    print("\nсводная оценка:")
    print(f"  ветка А (хвосты → golden): {total_cov:.0%} family-coverage ({agg_hit}/{agg_total})")
    ja = judge_res["aggregate"] if judge_res else None
    if ja and ja.get("judged"):
        print(f"  судья (все гипотезы, вне ранжирования): {ja['overall']}/5 "
              f"(оценено {ja['judged']}/{ja['n']})")
        for label, agg in judge_res["by_branch"].items():
            if agg.get("judged"):
                print(f"    {label}: {agg['overall']}/5")
    else:
        print("  судья: не оценивал (LLM недоступен / нет гипотез / --no-judge)")

if __name__ == "__main__":
    main()
