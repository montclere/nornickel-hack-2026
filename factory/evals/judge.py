from __future__ import annotations

import argparse
import hashlib
import json
import os

from factory.config import DEFAULT_CACHE, JUDGE_CACHE, JUDGE_MODEL, MAX_CHUNK_CHARS
from factory.ext.llm import Yandex, extract_json

RUBRIC_VERSION = "v1"

DIMENSIONS = {
    "grounding":    "обоснованность: подтверждена ли гипотеза приведёнными цитатами-источниками",
    "plausibility": "правдоподобность: физически ли осмыслен механизм для обогащения",
    "relevance":    "релевантность: работает ли гипотеза на заявленный KPI",
    "novelty":      "неочевидность: это нетривиальная связь, а не общеизвестный факт",
    "testability":  "проверяемость: может ли инженер поставить по ней конкретный эксперимент",
}
SCALE_MIN, SCALE_MAX = 1, 5

SYSTEM = ("Ты — старший инженер-обогатитель и научный рецензент. Оцениваешь "
          "СГЕНЕРИРОВАННУЮ гипотезу по фиксированной рубрике (шкала 1..5). Судишь строго "
          "и калиброванно: опираешься ТОЛЬКО на текст гипотезы и приведённые цитаты, "
          "ничего не додумываешь. Ответ — ТОЛЬКО JSON.")

PROMPT = """KPI (цель): {kpi}

ГИПОТЕЗА:
  ЕСЛИ: {hyp_if}
  ТО: {hyp_then}
  ПОТОМУ ЧТО: {hyp_because}

ЦИТАТЫ-ИСТОЧНИКИ (основание гипотезы):
{quotes}

Оцени по каждой оси целым баллом {smin}..{smax} и дай короткое обоснование (<=15 слов):
{rubric}

Верни СТРОГО JSON:
{{"grounding":{{"score":N,"reason":"..."}},"plausibility":{{"score":N,"reason":"..."}},
"relevance":{{"score":N,"reason":"..."}},"novelty":{{"score":N,"reason":"..."}},
"testability":{{"score":N,"reason":"..."}}}}"""

def _quotes_block(d) -> str:
    seen, lines = set(), []
    for e in getattr(d, "chain", None) or []:
        q = (e.get("quote") or "").strip()
        if not q or q in seen:
            continue
        seen.add(q)
        loc = e.get("locator") or e.get("source") or ""
        lines.append(f"  — «{q[:400]}»" + (f" [{loc}]" if loc else ""))
    if lines:
        return "\n".join(lines)
    for e in getattr(d, "evidence", None) or []:
        label, cell = e.get("label", ""), e.get("cell", "")
        if label:
            lines.append(f"  — {label}" + (f" [ячейка {cell}]" if cell else ""))
    return "\n".join(lines) if lines else "  (прямых цитат нет — структурный вывод графа)"

def _fingerprint(d, kpi) -> str:
    h = hashlib.sha256()
    h.update(RUBRIC_VERSION.encode()); h.update((kpi or "").encode())
    for part in (d.statement_if, d.statement_then, d.statement_because, _quotes_block(d)):
        h.update((part or "").encode("utf-8"))
    return h.hexdigest()[:16]

def _clamp_score(v):
    try:
        return max(SCALE_MIN, min(SCALE_MAX, int(round(float(v)))))
    except (TypeError, ValueError):
        return None

def _normalize(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    out = {}
    for dim in DIMENSIONS:
        cell = raw.get(dim)
        score = _clamp_score(cell.get("score")) if isinstance(cell, dict) else _clamp_score(cell)
        if score is None:
            return None
        reason = (cell.get("reason", "") if isinstance(cell, dict) else "")
        out[dim] = {"score": score, "reason": str(reason)[:200]}
    out["overall"] = round(sum(c["score"] for c in out.values()) / len(DIMENSIONS), 2)
    return out

class HypothesisJudge:

    def __init__(self, llm=None, model=JUDGE_MODEL):
        self.llm = llm or Yandex(model=model, temperature=0.0, max_tokens=800)

    @property
    def ready(self):
        return self.llm.ready

    def judge_one(self, d, kpi, attempts=2) -> dict | None:
        rubric = "\n".join(f"  - {k}: {v}" for k, v in DIMENSIONS.items())
        user = PROMPT.format(kpi=kpi or "—", hyp_if=d.statement_if, hyp_then=d.statement_then,
                             hyp_because=d.statement_because, quotes=_quotes_block(d),
                             rubric=rubric, smin=SCALE_MIN, smax=SCALE_MAX)

        for _ in range(max(1, attempts)):
            try:
                verdict = _normalize(extract_json(self.llm.complete(SYSTEM,
                                                                    user[:MAX_CHUNK_CHARS + 800])))
            except Exception:
                verdict = None
            if verdict is not None:
                return verdict
        return None

    def judge(self, discoveries, kpi="", cache_path=JUDGE_CACHE, log=lambda *a: None) -> dict:
        if not self.ready:
            raise RuntimeError("нет ключа Yandex (.env) — LLM-as-judge требует LLM")
        cache = {}
        if cache_path and os.path.exists(cache_path):
            try:
                cache = json.load(open(cache_path, encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                cache = {}

        items, dirty = [], False
        for i, d in enumerate(discoveries, 1):
            fp = _fingerprint(d, kpi)
            verdict = cache.get(fp)
            if verdict is None:
                verdict = self.judge_one(d, kpi)
                if verdict is not None:
                    cache[fp] = verdict; dirty = True
                log(f"  #{i}: судья {'—' if verdict is None else verdict['overall']}"
                    + (" (нечитаемо)" if verdict is None else ""))
            else:
                log(f"  #{i}: кэш {verdict['overall']}")
            items.append({"statement_if": d.statement_if, "score": getattr(d, "score", None),
                          "verdict": verdict})

        if dirty and cache_path:
            os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
            json.dump(cache, open(cache_path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        return {"items": items, "aggregate": self._aggregate(items),
                "rubric_version": RUBRIC_VERSION}

    @staticmethod
    def _aggregate(items) -> dict:
        judged = [it["verdict"] for it in items if it["verdict"]]
        agg = {"n": len(items), "judged": len(judged), "skipped": len(items) - len(judged)}
        if not judged:
            return agg
        for dim in DIMENSIONS:
            agg[dim] = round(sum(v[dim]["score"] for v in judged) / len(judged), 2)
        agg["overall"] = round(sum(v["overall"] for v in judged) / len(judged), 2)
        return agg

def _branch_b(cache_path, kpi, log):
    from factory.trackb.discover import discover
    from factory.trackb.extract import load_cached_relations
    from factory.trackb.kgraph import RelationGraph

    rels = load_cached_relations(cache_path, log)
    if not rels:
        log("  → нет данных: сначала запустите "
            "'python -m factory.flex <материалы> --kpi \"...\"'")
        return []
    kg = RelationGraph(rels)
    log(f"граф из кэша: {kg.stats()}")
    return discover(kg, kpi=kpi, limit=8)

def _branch_a(fabrics_dir, kpi, log):
    import glob

    from factory.pipeline import HypothesisFactory

    out = []
    for xlsx in sorted(glob.glob(os.path.join(fabrics_dir, "*", "Хвосты*.xlsx"))):
        res = HypothesisFactory(xlsx, kpi=kpi).run()
        fabric = res["profile"].fabric
        log(f"  хвосты/{fabric}: {len(res['hypotheses'])} гипотез")
        out.extend((fabric, h) for h in res["hypotheses"])
    return out

def _aggregate_by_branch(items) -> dict:
    from collections import defaultdict
    buckets = defaultdict(list)
    for it in items:
        buckets[it.get("branch", "?")].append(it)
    return {label: HypothesisJudge._aggregate(its) for label, its in buckets.items()}

def judge_everything(fabrics_dir=None, cache_path=None, kpi="", judge_cache=JUDGE_CACHE,
                     include_tailings=True, include_literature=True,
                     log=lambda *a: None) -> dict | None:
    judge = HypothesisJudge()
    if not judge.ready:
        return None

    records = []
    if include_tailings and fabrics_dir:
        for fabric, h in _branch_a(fabrics_dir, kpi, log):
            records.append({"branch": "хвосты", "fabric": fabric, "obj": h})
    if include_literature:
        for d in _branch_b(cache_path, kpi, log):
            records.append({"branch": "литература", "fabric": None, "obj": d})
    if not records:
        return None

    res = judge.judge([r["obj"] for r in records], kpi=kpi, cache_path=judge_cache, log=log)
    for r, item in zip(records, res["items"]):
        item["branch"], item["fabric"] = r["branch"], r["fabric"]
    res["records"] = records
    res["by_branch"] = _aggregate_by_branch(res["items"])
    return res

def main():
    import sys
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    ap = argparse.ArgumentParser(
        description="LLM-as-judge: оценка ВСЕХ гипотез системы (хвосты + литература). "
                    "Ветку Б наполняет ТОЛЬКО flex.py — запустите его первым.")
    ap.add_argument("--fabrics", default=os.path.join("materials", "data", "fabrics"),
                    help="папка с фабриками (Хвосты*.xlsx) — ветка А")
    ap.add_argument("--cache", default=DEFAULT_CACHE,
                    help="кэш графа, наполненный 'python -m factory.flex ...' — ветка Б")
    ap.add_argument("--no-tailings", action="store_true", help="не оценивать ветку А")
    ap.add_argument("--no-literature", action="store_true", help="не оценивать ветку Б")
    ap.add_argument("--kpi", default="", help="KPI для судьи; если не задан — берётся из "
                    "конфига последнего flex-запуска. Судья оценивает релевантность "
                    "гипотез ЭТОЙ цели")
    ap.add_argument("--judge-cache", default=JUDGE_CACHE)
    ap.add_argument("--no-cache", action="store_true", help="не кэшировать вердикты судьи")
    args = ap.parse_args()

    from factory.runconfig import resolve_kpi
    kpi, kpi_source = resolve_kpi(args.kpi)
    if not kpi:
        ap.error("--kpi не задан и не найден в конфиге последнего запуска "
                 f"({kpi_source}). Запустите сначала 'python -m factory.flex ... --kpi "
                 "\"...\"' либо передайте --kpi здесь.")

    log = lambda m: print("  " + m)
    print("LLM-as-judge — оценка всех гипотез системы")
    print(f"KPI: «{kpi}»  [источник: {kpi_source}]")

    judge = HypothesisJudge()

    if not judge.ready or not judge.llm.probe():
        print("LLM (Yandex) недоступен — судья пропущен."); return
    print("LLM (Yandex): доступен")

    res = judge_everything(
        fabrics_dir=args.fabrics, cache_path=args.cache, kpi=kpi,
        judge_cache=None if args.no_cache else args.judge_cache,
        include_tailings=not args.no_tailings, include_literature=not args.no_literature,
        log=log)
    if res is None:
        print("\nгипотез не найдено — нечего оценивать."); return

    print(f"\nвсего гипотез к оценке: {len(res['records'])}\n")
    for r, it in zip(res["records"], res["items"]):
        v = it["verdict"]
        tag = r["branch"] + (f"/{r['fabric']}" if r["fabric"] else "")
        if not v:
            print(f"  - [{tag}] [нечитаемо] {r['obj'].statement_if}"); continue
        dims = " ".join(f"{k[:4]}={v[k]['score']}" for k in DIMENSIONS)
        print(f"  [{tag}] судья={v['overall']}  {dims}")
        print(f"     {r['obj'].statement_if}")

    a = res["aggregate"]
    print()
    if a.get("judged"):
        dims = "  ".join(f"{k}={a[k]}" for k in DIMENSIONS)
        print(f"судейский балл (все гипотезы): {a['overall']}/5  "
              f"(оценено {a['judged']}/{a['n']}, пропущено {a['skipped']})")
        print(f"по осям: {dims}")
        for label, agg in res["by_branch"].items():
            if agg.get("judged"):
                print(f"  {label}: {agg['overall']}/5 (n={agg['judged']})")
    else:
        print("ни одной гипотезы не удалось оценить (LLM вернул нечитаемое).")
    print(f"рубрика {res['rubric_version']} — оценка вне ранжирования (LLM не в рассуждении)")

if __name__ == "__main__":
    main()
