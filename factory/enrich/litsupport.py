from __future__ import annotations

import math
import re

MIN_OVERLAP = 2
TOP_K = 2

def _stems(s: str) -> set:
    return {w[:6] for w in re.findall(r"[а-яёa-z]{4,}", (s or "").lower())}

def _hyp_stems(h) -> set:
    parts = [getattr(h, "intervention", ""), getattr(h, "family", ""),
             getattr(h, "dominant_form", "") or "",
             getattr(h, "statement_then", ""), getattr(h, "statement_because", "")]
    parts += list(getattr(h, "alternatives", []) or [])
    return _stems(" ".join(parts))

def _corpus_df(relations):
    df = {}
    for r in relations or []:
        rs = _stems(" ".join([r.get("subject", ""), r.get("object", ""), r.get("quote", "")]))
        for s in rs:
            df[s] = df.get(s, 0) + 1
    return df, len(relations or [])

def match_literature(h, relations: list, top_k: int = TOP_K, df=None) -> list:
    hs = _hyp_stems(h)
    if not hs:
        return []
    if df is None:
        df, _ = _corpus_df(relations)
    n_docs = max(len(relations or []), 1)
    scored = []
    for i, r in enumerate(relations or []):
        q = (r.get("quote") or "").strip()
        if not q:
            continue
        rs = _stems(" ".join([r.get("subject", ""), r.get("object", ""), q]))
        common = hs & rs
        if len(common) < MIN_OVERLAP:
            continue
        weight = sum(math.log((n_docs + 1) / (df.get(s, 0) + 0.5)) for s in common)
        scored.append((-round(weight, 4), -len(common), i))
    scored.sort()
    out, seen = [], set()
    for _, _, i in scored:
        r = relations[i]
        q = r["quote"].strip()
        if q in seen:
            continue
        seen.add(q)
        out.append({"quote": q, "locator": r.get("locator", ""),
                    "source": r.get("source", "") or (r.get("meta") or {}).get("file", ""),
                    "page": (r.get("meta") or {}).get("page"),
                    "subject": r.get("subject", ""), "object": r.get("object", "")})
        if len(out) >= top_k:
            break
    return out

def enrich(hyps, relations: list, log=lambda *a: None) -> int:
    if not relations:
        return 0
    df, _ = _corpus_df(relations)
    n = 0
    for h in hyps:
        lit = match_literature(h, relations, df=df)
        if lit:
            h.literature = lit
            n += 1
            log(f"  {h.size_class}/{h.family}: +{len(lit)} цитат из корпуса")
    return n
