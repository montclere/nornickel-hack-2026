# -*- coding: utf-8 -*-
"""Литературное подкрепление ветки А: дословные цитаты из ВЫДАННОГО корпуса на карточке.

Карточка гипотезы по хвостам до сих пор ссылалась на две статичные строки («Принцип
обогащения», «Инструкция…»). Здесь к ней детерминированно подбираются ЦИТАТЫ из
выданной литературы — те самые связи, что извлёк flex.py в кэш (extract.py, с цитатным
гейтом). Карточка становится трёхслойной: числа из отчёта (ячейки) + подтверждение из
базы знаний (цитата+страница) + мировая практика (веб). Это прямое требование ТЗ
(«обоснование + ссылки на источник») и ответ организаторов: источник обязателен,
знания из головы LLM — чёрный ящик.

НИКАКОГО LLM на этом шаге: лексический матч по СТЕМАМ (первые 6 букв слова — грубая,
но детерминированная защита от русской морфологии: «доизмельчение»/«доизмельчением»
дают один стем). Связь прикрепляется только при пересечении ≥2 стемов с текстом
вмешательства/семейства/формы — одиночное общее слово («класс») цитату не приносит.
Тот же кэш → тот же результат. Нет кэша/совпадений → блока просто нет (не выдумываем).
"""
from __future__ import annotations

import re

MIN_OVERLAP = 2      # минимум общих стемов гипотеза↔связь (защита от шумовых совпадений)
TOP_K = 2            # цитат на карточку — хватает для подтверждения, не раздувает отчёт


def _stems(s: str) -> set:
    return {w[:6] for w in re.findall(r"[а-яёa-z]{4,}", (s or "").lower())}


def _hyp_stems(h) -> set:
    parts = [getattr(h, "intervention", ""), getattr(h, "family", ""),
             getattr(h, "dominant_form", "") or ""] + list(getattr(h, "alternatives", []) or [])
    return _stems(" ".join(parts))


def match_literature(h, relations: list, top_k: int = TOP_K) -> list:
    """Топ-K связей корпуса, лексически подтверждающих гипотезу. Детерминированно:
    ранжируем по числу общих стемов, ничья решается порядком в кэше."""
    hs = _hyp_stems(h)
    if not hs:
        return []
    scored = []
    for i, r in enumerate(relations or []):
        q = (r.get("quote") or "").strip()
        if not q:
            continue
        rs = _stems(" ".join([r.get("subject", ""), r.get("object", ""), q]))
        ov = len(hs & rs)
        if ov >= MIN_OVERLAP:
            scored.append((-ov, i))
    scored.sort()
    out, seen = [], set()
    for _, i in scored:
        r = relations[i]
        q = r["quote"].strip()
        if q in seen:
            continue
        seen.add(q)
        out.append({"quote": q, "locator": r.get("locator", ""),
                    "source": r.get("source", ""),
                    "subject": r.get("subject", ""), "object": r.get("object", "")})
        if len(out) >= top_k:
            break
    return out


def enrich(hyps, relations: list, log=lambda *a: None) -> int:
    """Прикрепить literature к гипотезам. Возвращает число обогащённых карточек."""
    if not relations:
        return 0
    n = 0
    for h in hyps:
        lit = match_literature(h, relations)
        if lit:
            h.literature = lit
            n += 1
            log(f"  📚 {h.size_class}/{h.family}: +{len(lit)} цитат из корпуса")
    return n
