# -*- coding: utf-8 -*-
"""Научная аналитика поверх профиля. ДЕТЕРМИНИРОВАННО, без LLM.

  liberation_profile — кривая раскрытия по крупности (раскрытый/закрытый/извлекаемый %);
  optimal_grind      — «обрыв раскрытия»: до какой крупности измельчать;
  tradeoffs          — противоречия (измельчение крупных ↔ рост -10 шламов);
  form_breakdown     — форм-специфичная разбивка потерь (что извлекаемо, что нет и почему).
"""
from __future__ import annotations

from factory.reader import LIBERATED, LOCKED, SIZE_ORDER
from factory.rules import FORM_NOTES


def _ni_forms(cl):
    return [f for f in cl.forms if f.element == "Ni" and f.tonnes]


def liberation_profile(profile):
    """По классам крупности: доли раскрытого / закрытого / извлекаемого Ni."""
    rows = []
    for cl in profile.classes:
        forms = _ni_forms(cl)
        tot = sum(f.tonnes for f in forms)
        if tot <= 0:
            continue
        lib = sum(f.tonnes for f in forms if f.form == LIBERATED)
        lock = sum(f.tonnes for f in forms if f.form == LOCKED)
        rec = sum(f.tonnes for f in forms if f.recoverable)
        rows.append({"class": cl.size_class,
                     "liberated_pct": round(100 * lib / tot, 1),
                     "locked_pct": round(100 * lock / tot, 1),
                     "recoverable_pct": round(100 * rec / tot, 1),
                     "rec_tonnes": round(rec, 1)})
    # порядок крупности крупный→тонкий
    rows.sort(key=lambda r: SIZE_ORDER.index(r["class"]) if r["class"] in SIZE_ORDER else 99)
    return rows


def optimal_grind(lib_rows):
    """Найти «обрыв раскрытия»: самый крупный класс, где закрытого больше раскрытого.
    Рекомендация — измельчать мельче этой границы."""
    boundary = None
    for r in lib_rows:
        if r["locked_pct"] > r["liberated_pct"]:
            boundary = r["class"]        # ещё недораскрыто
        else:
            break                         # дошли до раскрытой зоны
    return boundary


def tradeoffs(profile, lib_rows):
    """Противоречия между вмешательствами (данные это подтверждают)."""
    out = []
    by = {r["class"]: r for r in lib_rows}
    coarse_locked = [r for r in lib_rows
                     if r["class"] not in ("-10", "-20+10") and r["locked_pct"] > 40]
    fines = by.get("-10")
    if coarse_locked and fines and fines["liberated_pct"] > 25:
        out.append(
            "Измельчение крупных классов раскроет закрытый Pnt, НО увеличит долю -10 мкм, "
            f"где уже {fines['liberated_pct']}% раскрытого Ni теряется со шламами. "
            "Нужен баланс: доизмельчение крупного + отдельная схема улавливания -10.")
    return out


def form_breakdown(profile):
    """Суммарно по формам (все классы): тонны Ni, извлекаемость и причина потери."""
    agg = {}
    for cl in profile.classes:
        for f in _ni_forms(cl):
            a = agg.setdefault(f.form, {"tonnes": 0.0, "recoverable": f.recoverable})
            a["tonnes"] += f.tonnes
    total = sum(a["tonnes"] for a in agg.values()) or 1.0
    rows = []
    for form, a in sorted(agg.items(), key=lambda kv: -kv[1]["tonnes"]):
        status, why = FORM_NOTES.get(form, ("—", ""))
        rows.append({"form": form, "tonnes": round(a["tonnes"], 1),
                     "share_pct": round(100 * a["tonnes"] / total, 1),
                     "recoverable": a["recoverable"], "status": status, "why": why})
    return rows


def analyze(profile):
    lib = liberation_profile(profile)
    return {"liberation": lib, "optimal_grind": optimal_grind(lib),
            "tradeoffs": tradeoffs(profile, lib), "forms": form_breakdown(profile)}
