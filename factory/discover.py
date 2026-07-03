# -*- coding: utf-8 -*-
"""Генерация гипотез из канонического графа. ДЕТЕРМИНИРОВАННО поверх извлечённых связей.

Стратегии (без LLM в логике):
  gaps      — разрывы Свонсона: A→B и B→C есть, прямого A→C нет → скрытая связь;
  novelty   — редкость: чем меньше связность концов, тем новее (структурная новизна).
Ранжирование прозрачно: novelty · relevance · (знак-согласованность).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache


@lru_cache(maxsize=None)
def _tokens(s):
    return frozenset(re.findall(r"[а-яёa-z]{4,}", (s or "").lower()))


@lru_cache(maxsize=None)
def _sim(a, b):
    """Похожесть узлов по токенам. Кэшируется: find_gaps сравнивает пары O(E²) раз."""
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0


@dataclass
class Discovery:
    a: str
    b: str
    c: str
    sign: int
    chain: list                      # [(edge_data), (edge_data)]
    novelty: float = 0.0
    relevance: float = 0.0
    score: float = 0.0
    statement_if: str = ""
    statement_then: str = ""
    statement_because: str = ""
    sources: list = field(default_factory=list)


def find_gaps(kg, thr=0.5):
    """A→B, B→C есть, прямого A→C нет (нечёткий матч сущностей)."""
    edges = [(u, v, d) for u, v, d in kg.g.edges(data=True)]
    direct = {(u, v) for u, v, _ in edges}
    out, seen = [], set()
    for a, b, d1 in edges:
        for b2, c, d2 in edges:
            if _sim(b, b2) < thr or _sim(a, c) >= thr:
                continue
            if (a, c) in direct or any(_sim(a, u) >= thr and _sim(c, v) >= thr
                                       for u, v, _ in edges):
                continue
            key = (a, c)
            if key in seen:
                continue
            seen.add(key)
            sign = 1 if d1.get("sign", 0) * d2.get("sign", 0) >= 0 else -1
            out.append((a, b, c, sign, [d1, d2]))
    return out


def find_direct(kg, kpi_tokens, thr=1):
    """Прямые рычаги: связь, чей ОБЪЕКТ близок к KPI → гипотеза «влиять на цель через X».
    Работает даже на разреженном графе (не нужны цепочки)."""
    out, seen = [], set()
    for u, v, d in kg.g.edges(data=True):
        if len(_tokens(v) & kpi_tokens) < thr:      # объект связан с целью KPI
            continue
        if (u, v) in seen:
            continue
        seen.add((u, v))
        out.append((u, kg.label(v), v, d.get("sign", 0), [d]))
    return out


def score(kg, cands, kpi_tokens=None, kind="gap"):
    kpi_tokens = kpi_tokens or set()
    res = []
    for a, b, c, sign, chain in cands:
        deg = kg.g.degree(a) + kg.g.degree(c)
        novelty = round(1.0 / (1 + deg), 3)
        relevance = round(len(_tokens(c) & kpi_tokens) / (len(kpi_tokens) or 1), 3) \
            if kpi_tokens else 0.5
        d = Discovery(a=kg.label(a), b=kg.label(b) if kind == "gap" else "",
                      c=kg.label(c), sign=sign, chain=chain,
                      novelty=novelty, relevance=relevance,
                      score=round(novelty * (0.4 + 0.6 * (relevance or 0.2)), 4),
                      sources=sorted({e.get("locator", "") for e in chain}))
        d.statement_if = f"воздействовать на «{d.c}» через «{d.a}»"
        d.statement_then = ("повысит" if sign > 0 else "снизит" if sign < 0 else "изменит") + f" «{d.c}»"
        if kind == "gap":
            d.statement_because = (f"«{d.a}»→«{d.b}» и «{d.b}»→«{d.c}», но прямой связи "
                                   f"«{d.a}»→«{d.c}» в корпусе нет (разрыв Свонсона)")
        else:
            q = chain[0].get("quote", "")
            d.statement_because = f"источник прямо связывает «{d.a}» и «{d.c}»: «{q[:120]}»"
        res.append(d)
    res.sort(key=lambda x: -x.score)
    return res


def discover(kg, kpi="", limit=10):
    kt = _tokens(kpi)
    gaps = score(kg, find_gaps(kg), kt, kind="gap")
    direct = score(kg, find_direct(kg, kt), kt, kind="direct")
    # дедуп по (a,c); разрывы приоритетнее прямых
    seen, merged = set(), []
    for d in gaps + direct:
        key = (d.a.lower(), d.c.lower())
        if key in seen:
            continue
        seen.add(key); merged.append(d)
    merged.sort(key=lambda x: -x.score)
    return merged[:limit]
