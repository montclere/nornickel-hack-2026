# -*- coding: utf-8 -*-
"""Детерминированные метрики гипотезы — БЕЗ денег. Всё из данных отчёта.

Ценность оцениваем безразмерно (не в валюте, которая зависит от поставщика/котировок):
  impact         — доля извлекаемых потерь фабрики, приходящаяся на класс (масштаб проблемы);
  addressability — какая часть потерь класса вообще извлекаема (насколько «излечимо»);
  clarity        — доминирование одной минеральной формы = ЯСНОСТЬ механизма (научная,
                   проверяемость: чем чётче форма, тем однозначнее гипотеза);
  confidence     — полнота данных под гипотезой;
  feasibility    — реализуемость (нужно ли новое оборудование).
Приоритет = impact · addressability · feasibility · confidence. Тоннаж — физический факт.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Metrics:
    rec_tonnes: dict          # {"Ni": т, "Cu": т} извлекаемого металла — ФАКТ из данных
    impact: float             # доля извлекаемых потерь фабрики (0..1) — масштаб
    addressability: float     # извлекаемая доля потерь класса (0..1) — «излечимость»
    clarity: float            # доминирование формы (0..1) — ясность механизма (научная)
    confidence: float         # полнота данных (0..1)
    feasibility: float        # реализуемость (0..1)
    priority: float           # impact · addressability · feasibility · confidence

    def as_dict(self):
        return {"rec_tonnes": {k: round(v, 1) for k, v in self.rec_tonnes.items()},
                "impact": round(self.impact, 3), "addressability": round(self.addressability, 3),
                "clarity": round(self.clarity, 3), "confidence": round(self.confidence, 2),
                "feasibility": round(self.feasibility, 2), "priority": round(self.priority, 4)}


class Scorer:
    """Считает безразмерные метрики по данным профиля. Все веса — явные."""

    def _rec_total(self, cl) -> float:
        return sum(cl.recoverable_tonnes(el) for el in ("Ni", "Cu"))

    def _class_total(self, cl) -> float:
        return sum(cl.tonnes.get(el) or 0.0 for el in ("Ni", "Cu"))

    def _clarity(self, cl) -> float:
        """Доля доминирующей извлекаемой формы среди извлекаемых (ясность механизма)."""
        rec_forms = [f for f in cl.forms if f.element == "Ni" and f.recoverable and f.tonnes]
        if not rec_forms:
            return 0.0
        tot = sum(f.tonnes for f in rec_forms)
        return max(f.tonnes for f in rec_forms) / tot if tot else 0.0

    def confidence(self, cl) -> float:
        forms = [f for f in cl.forms if f.element == "Ni"]
        if not forms:
            return 0.3
        return 1.0 if any(f.tonnes for f in forms) else 0.6

    def score_all(self, profile, diagnoses: dict):
        rec_by = {cl.size_class: self._rec_total(cl) for cl in profile.classes}
        total_rec = sum(rec_by.values()) or 1.0
        out = {}
        for cl in profile.classes:
            diag = diagnoses.get(cl.size_class)
            rec = {el: cl.recoverable_tonnes(el) for el in ("Ni", "Cu")}
            impact = rec_by[cl.size_class] / total_rec
            ctot = self._class_total(cl)
            addressability = (rec_by[cl.size_class] / ctot) if ctot else 0.0
            feas = 1.0 if (diag and not diag.needs_equipment) else 0.6
            conf = self.confidence(cl)
            adr = min(addressability, 1.0)
            # приоритет ВЕДЁТ масштаб (impact); излечимость модулирует ±, не доминирует
            priority = impact * (0.5 + 0.5 * adr) * feas * conf
            out[cl.size_class] = Metrics(
                rec_tonnes=rec, impact=impact, addressability=adr,
                clarity=self._clarity(cl), confidence=conf, feasibility=feas,
                priority=round(priority, 5))
        return out
