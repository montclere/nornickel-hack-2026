# -*- coding: utf-8 -*-
"""Научная аналитика поверх профиля. ДЕТЕРМИНИРОВАННО, без LLM.

  liberation_profile — кривая раскрытия по крупности (раскрытый/закрытый/извлекаемый %);
  optimal_grind      — «обрыв раскрытия»: до какой крупности измельчать;
  tradeoffs          — противоречия (измельчение крупных ↔ рост -10 шламов);
  form_breakdown     — форм-специфичная разбивка потерь (что извлекаемо, что нет и почему).

Всё считается по ЦЕЛЕВОМУ элементу (см. intent.py) — раньше было зашито «Ni».
"""
from __future__ import annotations

from factory.reader import LIBERATED, LOCKED, PRIMARY_ELEMENT, class_sort_key
from factory.rules import FORM_NOTES


def _target_forms(cl, element):
    return [f for f in cl.forms if f.element == element and f.tonnes]


def liberation_profile(profile, element):
    """По классам крупности: доли раскрытого / закрытого / извлекаемого (по element)."""
    rows = []
    for cl in profile.classes:
        forms = _target_forms(cl, element)
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
    # порядок крупности крупный→тонкий — без белого списка, по числу в подписи
    rows.sort(key=lambda r: class_sort_key(r["class"]))
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


def tradeoffs(profile, lib_rows, element):
    """Противоречия между вмешательствами (данные это подтверждают)."""
    out = []
    by = {r["class"]: r for r in lib_rows}
    coarse_locked = [r for r in lib_rows
                     if r["class"] not in ("-10", "-20+10") and r["locked_pct"] > 40]
    fines = by.get("-10")
    if coarse_locked and fines and fines["liberated_pct"] > 25:
        out.append(
            f"Измельчение крупных классов раскроет закрытый {element}-содержащий минерал, "
            f"НО увеличит долю -10 мкм, где уже {fines['liberated_pct']}% раскрытого "
            f"{element} теряется со шламами. Нужен баланс: доизмельчение крупного + "
            f"отдельная схема улавливания -10.")
    return out


def form_breakdown(profile, element):
    """Суммарно по формам (все классы): тонны element, извлекаемость и причина потери."""
    agg = {}
    for cl in profile.classes:
        for f in _target_forms(cl, element):
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


def analyze(profile, element: str = PRIMARY_ELEMENT):
    lib = liberation_profile(profile, element)
    return {"element": element, "liberation": lib, "optimal_grind": optimal_grind(lib),
            "tradeoffs": tradeoffs(profile, lib, element),
            "forms": form_breakdown(profile, element)}
