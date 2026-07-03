#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бейзлайн 1 — ЛИТЕРАТУРНЫЙ LBD (разрывы Свонсона). УНИВЕРСАЛЬНЫЙ ДВИЖОК.

В этом файле — ТОЛЬКО домен-независимая логика:
    корпус → триплеты → граф → поиск незакрытых звеньев A→C → скоринг.
Ни одной доменной строки (нет «никель», «пентландит», «извлечение» и т.п.).

Весь домен вынесен во ВНЕШНИЙ конфиг `domains/<name>.json`:
    kpi_keywords, relations (лексикон связей), stopwords, corpus.
Смена домена = другой JSON, КОД НЕ МЕНЯЕТСЯ. Это и есть проверка универсальности.

Запуск:
    python run.py                          # домен по умолчанию (flotation)
    python run.py domains/alloys.json      # другой домен — тот же движок
    python run.py domains/flotation.json domains/alloys.json   # оба подряд

Зависимости: только стандартная библиотека Python 3.9+.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

_n = [0]
def step(msg):
    _n[0] += 1; print(f"\n[{_n[0]:>2}] ── {msg}")
def sub(msg):
    print(f"        {msg}")

HERE = os.path.dirname(__file__)


# ─────────────────────────────────────────────────────────────────────────────
# Экстрактор триплетов (правиловый, с провенансом). Работает по ЛЕКСИКОНУ из
# конфига — сам не знает ни одного доменного слова. В проде здесь LLM.
# ─────────────────────────────────────────────────────────────────────────────
def extract_triplets(corpus, relations, stopwords):
    def canon(s):
        words = [w for w in s.strip().lower().split() if w not in stopwords]
        return " ".join(words).strip()

    triplets = []
    for doc_id, sent in corpus:
        low = sent.lower()
        for pat, sign in relations:
            m = re.search(pat, low)
            if not m:
                continue
            head = canon(sent[:m.start()].strip(" .,"))
            tail = canon(sent[m.end():].strip(" .,"))
            if head and tail:
                triplets.append({"head": head, "sign": sign, "tail": tail,
                                 "doc_id": doc_id, "quote": sent})
            break
    return triplets


# ─────────────────────────────────────────────────────────────────────────────
# Граф + LBD (разрывы Свонсона). Полностью домен-независимо.
# ─────────────────────────────────────────────────────────────────────────────
def out_edges(edges, node):
    return [e for e in edges if e["head"] == node]


def find_open_links(edges):
    direct = {(e["head"], e["tail"]) for e in edges}
    cands = []
    for ab in edges:
        a, b = ab["head"], ab["tail"]
        for bc in out_edges(edges, b):
            c = bc["tail"]
            if c == a or (a, c) in direct:
                continue
            sign = "+" if ab["sign"] == bc["sign"] else "-"
            cands.append({"a": a, "b": b, "c": c, "sign": sign, "chain": [ab, bc]})
    seen, uniq = set(), []
    for cand in sorted(cands, key=lambda x: (x["a"], x["c"], x["b"])):
        if (cand["a"], cand["c"]) in seen:
            continue
        seen.add((cand["a"], cand["c"])); uniq.append(cand)
    return uniq


# ─────────────────────────────────────────────────────────────────────────────
# Прозрачный скоринг. Ценность = близость конца цепочки к KPI (термины из конфига),
# а НЕ зашитое слово. Веса редактируются экспертом.
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_WEIGHTS = {"novelty": 1.0, "value": 1.2, "risk": -1.0}

def score(cand, edges, kpi_keywords, weights):
    a, c = cand["a"], cand["c"]
    deg = len(out_edges(edges, a)) + len([e for e in edges if e["tail"] == c])
    novelty = 1.0 / (1 + deg)
    value = 1.0 if any(k in c for k in kpi_keywords) else 0.5
    risk = 0.5 if cand["sign"] == "-" else 0.2
    feats = {"novelty": round(novelty, 3), "value": value, "risk": risk}
    total = round(sum(weights.get(k, 0) * v for k, v in feats.items()), 3)
    return total, feats


def make_hypothesis(cand, edges, kpi_keywords, weights):
    total, feats = score(cand, edges, kpi_keywords, weights)
    direction = "повысит" if cand["sign"] == "+" else "изменит"
    return {
        "if": f"воздействовать на «{cand['c']}» через «{cand['a']}»",
        "then": f"{direction} «{cand['c']}»",
        "because": (f"«{cand['a']}» влияет на «{cand['b']}», а «{cand['b']}» — на "
                    f"«{cand['c']}»; прямой связи «{cand['a']}»→«{cand['c']}» в корпусе "
                    f"нет (разрыв Свонсона)"),
        "chain": cand["chain"], "score": total, "features": feats,
        "sources": sorted({e["doc_id"] for e in cand["chain"]}),
    }


# ─────────────────────────────────────────────────────────────────────────────
def run_domain(path):
    dom = json.load(open(path, encoding="utf-8"))
    relations = [(p, s) for p, s in dom["relations"]]
    kpi = dom.get("kpi_keywords", [])
    print("\n" + "=" * 78)
    print(f"ДОМЕН: {dom['name']}   (конфиг: {os.path.basename(path)})")
    print("=" * 78)

    step(f"Корпус: {len(dom['corpus'])} предложений; KPI-термины: {kpi}")
    for d, s in dom["corpus"]:
        sub(f"[{d}] {s}")

    step("Извлекаю триплеты по лексикону связей из конфига (провенанс до предложения)")
    triplets = extract_triplets(dom["corpus"], relations, set(dom.get("stopwords", [])))
    for t in triplets:
        sub(f"({t['head']}) —[{t['sign']}]→ ({t['tail']})   [{t['doc_id']}]")

    step("Строю граф и ищу незакрытые звенья A→C (LBD Свонсона)")
    edges = triplets
    cands = find_open_links(edges)
    sub(f"рёбер: {len(edges)}, кандидатов-гипотез: {len(cands)}")

    step("Формулирую и ранжирую (веса по умолчанию, ценность = близость к KPI)")
    hyps = sorted((make_hypothesis(c, edges, kpi, DEFAULT_WEIGHTS) for c in cands),
                  key=lambda h: -h["score"])
    for i, h in enumerate(hyps, 1):
        print(f"\n   #{i}  score={h['score']}  features={h['features']}")
        print(f"       ЕСЛИ:  {h['if']}")
        print(f"       ТО:    {h['then']}")
        print(f"       П.Ч.:  {h['because']}")
        for e in h["chain"]:
            print(f"       ↳ [{e['doc_id']}] «{e['quote']}»")

    step("ЭКСПЕРТНАЯ КОРРЕКТИРОВКА: поднимаю вес риска (risk: -1.0 → -3.0)")
    w2 = dict(DEFAULT_WEIGHTS, risk=-3.0)
    for i, h in enumerate(sorted((make_hypothesis(c, edges, kpi, w2) for c in cands),
                                 key=lambda h: -h["score"]), 1):
        sub(f"  #{i}  score={h['score']:>6}  {h['then']}")

    step("Хук агента-поисковика — заглушка (доисследование топ-гипотезы)")
    sub(research(hyps[0]["if"]) if hyps else "нет гипотез")


def research(query: str) -> str:
    # TODO(agent): подключить поисковый агент (веб/Semantic Scholar/патенты).
    return f"[research-stub] здесь агент доисследует и проверит новизну: «{query}»"


def main():
    args = sys.argv[1:]
    if not args:
        args = [os.path.join(HERE, "domains", "flotation.json")]
    for a in args:
        run_domain(a if os.path.isabs(a) or os.path.exists(a) else os.path.join(HERE, a))
    print("\n" + "=" * 78)
    print("Один движок, разные JSON-домены. В КОДЕ нет ни одного доменного слова —")
    print("вся специфика во внешнем конфиге. Это и есть универсальность (не хардкод).")
    print("=" * 78)


if __name__ == "__main__":
    main()
