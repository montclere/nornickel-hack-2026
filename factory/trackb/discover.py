from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache


@lru_cache(maxsize=None)
def _tokens(s):
    return frozenset(re.findall(r"[а-яёa-z]{4,}", (s or "").lower()))

@lru_cache(maxsize=None)
def _sim(a, b):
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0

@dataclass
class Discovery:
    a: str
    b: str
    c: str
    sign: int
    chain: list
    novelty: float = 0.0
    relevance: float = 0.0
    is_action: bool = False
    role: str = "reference"
    score: float = 0.0
    statement_if: str = ""
    statement_then: str = ""
    statement_because: str = ""
    sources: list = field(default_factory=list)

def find_gaps(kg, thr=0.5):
    edges = [(u, v, d) for u, v, d in kg.g.edges(data=True)]
    direct = {(u, v) for u, v, _ in edges}
    out, seen = [], set()
    for a, b, d1 in edges:
        for b2, c, d2 in edges:
            if _sim(b, b2) < thr or _sim(a, c) >= thr:
                continue
            if (a, c) in direct or (a, c) in seen:
                continue
            seen.add((a, c))
            sign = 1 if d1.get("sign", 0) * d2.get("sign", 0) >= 0 else -1
            out.append((a, b, c, sign, [d1, d2]))
    return out

def _corpus_df(kg):
    df = {}
    for n in kg.g.nodes():
        for t in _tokens(kg.label(n)):
            df[t] = df.get(t, 0) + 1
    return df, (kg.g.number_of_nodes() or 1)

def _novelty(a_label, c_label, df, n_nodes):
    toks = _tokens(a_label) | _tokens(c_label)
    if not toks:
        return 0.0
    return round(sum(1 - df.get(t, 0) / n_nodes for t in toks) / len(toks), 3)

def find_direct(kg, kpi_tokens, thr=1):
    out, seen = [], set()
    for u, v, d in kg.g.edges(data=True):
        hay = _tokens(v) | _tokens(u) | _tokens(d.get("quote", ""))
        if len(hay & kpi_tokens) < thr:
            continue
        if (u, v) in seen:
            continue
        seen.add((u, v))
        out.append((u, kg.label(v), v, d.get("sign", 0), [d]))
    return out

def _all_as_direct(kg):
    return [(u, kg.label(v), v, d.get("sign", 0), [d]) for u, v, d in kg.g.edges(data=True)]

_NON_ACTION_PENALTY = 0.6

_STATE_BONUS = 1.15

def score(kg, cands, kpi_tokens=None, kind="gap"):
    kpi_tokens = kpi_tokens or set()
    df, n_nodes = _corpus_df(kg)
    res = []
    for a, b, c, sign, chain in cands:
        novelty = _novelty(kg.label(a), kg.label(c), df, n_nodes)

        hay = _tokens(kg.label(a)) | _tokens(kg.label(c)) | _tokens(chain[0].get("quote", ""))
        relevance = round(len(hay & kpi_tokens) / (len(kpi_tokens) or 1), 3) \
            if kpi_tokens else 0.5

        is_action = bool(chain[0].get("is_action", False))
        role = chain[0].get("role", "reference")
        base = novelty * (0.4 + 0.6 * (relevance or 0.2))
        base = base if is_action else base * _NON_ACTION_PENALTY
        base = base * _STATE_BONUS if role == "state" else base
        d = Discovery(a=kg.label(a), b=kg.label(b) if kind == "gap" else "",
                      c=kg.label(c), sign=sign, chain=chain,
                      novelty=novelty, relevance=relevance, is_action=is_action, role=role,
                      score=round(base, 4),
                      sources=sorted({e.get("locator", "") for e in chain}))
        verb = "повысит" if sign > 0 else "снизит" if sign < 0 else "изменит"
        if is_action:

            d.statement_if = f"внедрить/применить «{d.a}» (целевой параметр «{d.c}»)"
            d.statement_then = f"{verb} «{d.c}»"
        else:

            d.statement_if = f"исследовать применимость к фабрике: «{d.a}» → «{d.c}»"
            d.statement_then = (f"фактор, потенциально влияющий на «{d.c}» "
                                f"(требует уточнения, чем это реализовать на фабрике)")
        if kind == "gap":
            d.statement_because = (f"«{d.a}»→«{d.b}» и «{d.b}»→«{d.c}», но прямой связи "
                                   f"«{d.a}»→«{d.c}» в корпусе нет (разрыв Свонсона)")
        else:
            q = chain[0].get("quote", "")
            d.statement_because = f"источник прямо связывает «{d.a}» и «{d.c}»: «{q[:120]}»"
        res.append(d)
    res.sort(key=lambda x: -x.score)
    return res

def _dedup(discoveries):
    seen, out = set(), []
    for d in discoveries:
        key = (d.a.lower(), d.c.lower())
        if key in seen:
            continue
        seen.add(key); out.append(d)
    return out

_EL_TERMS = {
    "Ni": {"nickel", "никел", "пентландит", "pentlandite", "миллерит", "millerite"},
    "Cu": {"copper", "медь", "меди", "медн", "халькопирит", "chalcopyrite", "халькозин"},
    "Co": {"cobalt", "кобальт"}, "Pt": {"platin", "платин"}, "Pd": {"pallad", "паллад"},
    "Au": {"gold", "золот"}, "Ag": {"silver", "серебр"}, "Fe": {"iron", "желез"},
}

def _el_terms(elements) -> set:
    out = set()
    for e in elements or []:
        out |= _EL_TERMS.get(e, set())
    return out

def discover(kg, kpi="", limit=10, breadth=0.0, elements=None):
    kt = _tokens(kpi)
    gaps = score(kg, find_gaps(kg), kt, kind="gap")
    direct = score(kg, find_direct(kg, kt), kt, kind="direct")
    merged = _dedup(gaps + direct)
    elt = _el_terms(elements)
    if elt:
        def _on_el(d):
            blob = f"{d.a} {d.c} {d.chain[0].get('quote','') if d.chain else ''}".lower()
            return any(t in blob for t in elt)
        on_metal = [d for d in merged if _on_el(d)]
        if on_metal:
            merged = on_metal
    if kt:
        grounded = [d for d in merged if d.relevance > 0]
        if grounded and breadth <= 0:
            merged = grounded
        elif grounded:

            rest = sorted((d for d in merged if d.relevance <= 0),
                          key=lambda x: -x.novelty)
            k = round(min(1.0, breadth) * min(len(rest), limit))
            merged = grounded + rest[:k]
        elif kg.g.number_of_edges():
            merged = _dedup(merged + score(kg, _all_as_direct(kg), kt, kind="direct"))
    elif len(merged) < limit and kg.g.number_of_edges():
        merged = _dedup(merged + score(kg, _all_as_direct(kg), kt, kind="direct"))
    merged.sort(key=lambda x: (-x.relevance, -x.score))
    return merged[:limit]
