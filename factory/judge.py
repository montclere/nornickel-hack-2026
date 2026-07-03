# -*- coding: utf-8 -*-
"""LLM-as-judge — качественная метрика ветки Б (гипотезы из discover.py).

Зачем: у детерминированной ветки А есть golden-бенчмарк, у ветки Б метрики не было.
Судья читает КАЖДУЮ сгенерированную гипотезу вместе с её источниками-цитатами и
выставляет баллы по фиксированной рубрике. Это ОЦЕНОЧНЫЙ слой: он НЕ участвует в
ранжировании (инвариант проекта — LLM не в рассуждении), а лишь измеряет качество.

Воспроизводимость:
  • temperature=0;
  • каждый вердикт кэшируется по отпечатку (рубрика+KPI+текст гипотезы) → тот же
    вход даёт тот же балл и не тратит квоту повторно (как кэш извлечения).

Заземление: судья видит дословные цитаты источников гипотезы, поэтому оценивает
ОБОСНОВАННОСТЬ, а не только поверхностную правдоподобность.

Замечание о смещении: по умолчанию судья — та же модель Yandex, что и экстрактор,
т.е. возможно self-preference bias. Модель судьи вынесена в JUDGE_MODEL и заменяема —
для строгой оценки поставьте судью сильнее/иного семейства.

Запуск:
    uv run python -m factory.judge materials/reference --kpi "снизить потери никеля"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

from factory.config import JUDGE_CACHE, JUDGE_MODEL, DEFAULT_KPI, MAX_CHUNK_CHARS, OUTPUTS_DIR
from factory.llm import Yandex, extract_json

RUBRIC_VERSION = "v1"

# ось → человекочитаемое пояснение (идёт и в промпт, и в вывод)
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
    """Дословные цитаты из цепочки связей гипотезы (с локатором-провенансом)."""
    seen, lines = set(), []
    for e in getattr(d, "chain", []) or []:
        q = (e.get("quote") or "").strip()
        if not q or q in seen:
            continue
        seen.add(q)
        loc = e.get("locator") or e.get("source") or ""
        lines.append(f"  — «{q[:400]}»" + (f" [{loc}]" if loc else ""))
    return "\n".join(lines) if lines else "  (прямых цитат нет — структурный вывод графа)"


def _fingerprint(d, kpi) -> str:
    """Отпечаток входа судьи: рубрика+KPI+текст гипотезы+цитаты. Меняется вход → перекэш."""
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
    """Привести ответ LLM к {ось: {score:int, reason:str}}; None — если нечитаемо."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for dim in DIMENSIONS:
        cell = raw.get(dim)
        score = _clamp_score(cell.get("score")) if isinstance(cell, dict) else _clamp_score(cell)
        if score is None:
            return None                      # неполный вердикт не засчитываем
        reason = (cell.get("reason", "") if isinstance(cell, dict) else "")
        out[dim] = {"score": score, "reason": str(reason)[:200]}
    out["overall"] = round(sum(c["score"] for c in out.values()) / len(DIMENSIONS), 2)
    return out


class HypothesisJudge:
    """Оценивает гипотезы ветки Б по рубрике. Кэш делает вердикты воспроизводимыми."""

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
        # LLM недетерминирован даже при t=0 → пара попыток против случайного мусора
        for _ in range(max(1, attempts)):
            try:
                verdict = _normalize(extract_json(self.llm.complete(SYSTEM,
                                                                    user[:MAX_CHUNK_CHARS + 800])))
            except Exception:  # noqa: BLE001
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


def _branch_b(paths, kpi, max_chunks, cache_path, log):
    """Ветка Б: приём → извлечение → граф → discover. Возвращает список Discovery."""
    from factory.discover import discover
    from factory.extract import extract_relations
    from factory.ingest import ingest, split
    from factory.kgraph import KnowledgeGraph

    chunks = split(ingest(paths))
    rels = extract_relations(chunks, max_chunks=max_chunks, query=kpi,
                             cache_path=cache_path, log=log)
    kg = KnowledgeGraph(rels)
    log(f"граф: {kg.stats()}")
    return discover(kg, kpi=kpi, limit=8)


def main():
    ap = argparse.ArgumentParser(description="LLM-as-judge: оценка гипотез ветки Б")
    ap.add_argument("paths", nargs="+", help="файлы/папки с литературой (знание)")
    ap.add_argument("--kpi", default=DEFAULT_KPI)
    ap.add_argument("--max-chunks", type=int, default=14)
    ap.add_argument("--extract-cache", default=os.path.join(OUTPUTS_DIR, "kb_cache.json"))
    ap.add_argument("--judge-cache", default=JUDGE_CACHE)
    ap.add_argument("--no-cache", action="store_true", help="не читать/писать кэши")
    args = ap.parse_args()

    log = lambda m: print("  " + m)
    print("=" * 74)
    print("LLM-AS-JUDGE · ОЦЕНКА ГИПОТЕЗ ВЕТКИ Б")
    print(f"KPI: {args.kpi}")
    print("=" * 74)

    judge = HypothesisJudge()
    if not judge.ready:
        print("⚠ нет ключа Yandex (.env) — судья недоступен."); return

    ecache = None if args.no_cache else args.extract_cache
    found = _branch_b(args.paths, args.kpi, args.max_chunks, ecache, log)
    print(f"\nгипотез к оценке: {len(found)}\n")
    if not found:
        print("гипотез не найдено — нечего оценивать."); return

    jcache = None if args.no_cache else args.judge_cache
    res = judge.judge(found, kpi=args.kpi, cache_path=jcache, log=log)

    print("\n" + "─" * 74)
    for it, d in zip(res["items"], found):
        v = it["verdict"]
        if not v:
            print(f"  · [нечитаемо] {d.statement_if}"); continue
        dims = " ".join(f"{k[:4]}={v[k]['score']}" for k in DIMENSIONS)
        print(f"  ■ судья={v['overall']}  {dims}")
        print(f"     {d.statement_if}")
    a = res["aggregate"]
    print("\n" + "=" * 74)
    if a.get("judged"):
        dims = " · ".join(f"{k}={a[k]}" for k in DIMENSIONS)
        print(f"СУДЕЙСКИЙ БАЛЛ ВЕТКИ Б: {a['overall']}/5  "
              f"(оценено {a['judged']}/{a['n']}, пропущено {a['skipped']})")
        print(f"по осям: {dims}")
    else:
        print("ни одной гипотезы не удалось оценить (LLM вернул нечитаемое).")
    print(f"рубрика {res['rubric_version']} · оценка вне ранжирования (LLM не в рассуждении)")
    print("=" * 74)


if __name__ == "__main__":
    main()
