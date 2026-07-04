# -*- coding: utf-8 -*-
"""Детерминированные метрики гипотезы — БЕЗ денег. Всё из данных отчёта.

Ценность оцениваем безразмерно (не в валюте, которая зависит от поставщика/котировок):
  impact         — доля извлекаемых потерь фабрики, приходящаяся на класс (масштаб проблемы);
  addressability — какая часть потерь класса вообще извлекаема (насколько «излечимо»);
  clarity        — доминирование одной минеральной формы = ЯСНОСТЬ механизма (научная,
                   проверяемость: чем чётче форма, тем однозначнее гипотеза);
  confidence     — полнота данных под гипотезой;
  feasibility    — реализуемость (нужно ли новое оборудование).
Приоритет (НАША эвристическая свёртка, не факт — объяснена в глоссарии):
  priority = impact · (0.5+0.5·addressability) · (0.7+0.3·clarity) · feasibility · confidence.
Ведёт масштаб (impact — факт из данных), остальное модулирует. Тоннаж — физический факт.
"""
from __future__ import annotations

from dataclasses import dataclass

from factory.reader import ELEMENT_SYMBOLS, PRIMARY_ELEMENT


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
    """Считает безразмерные метрики по данным профиля. Все веса — явные.

    `element` — целевой элемент KPI (см. intent.py); импакт/адресуемость/ясность
    считаются ПО НЕМУ, а не по зашитому первому элементу отчёта. rec_tonnes в выводе
    всё равно несёт оба элемента — для контекста на карточке."""

    def _rec_total(self, cl, element) -> float:
        return cl.recoverable_tonnes(element)

    def _class_total(self, cl, element) -> float:
        return cl.tonnes.get(element) or 0.0

    def _clarity(self, cl, element) -> float:
        """Доля доминирующей извлекаемой формы среди извлекаемых (ясность механизма)."""
        rec_forms = [f for f in cl.forms
                     if f.element == element and f.recoverable and f.tonnes]
        if not rec_forms:
            return 0.0
        tot = sum(f.tonnes for f in rec_forms)
        return max(f.tonnes for f in rec_forms) / tot if tot else 0.0

    def confidence(self, cl, element) -> float:
        forms = [f for f in cl.forms if f.element == element]
        if not forms:
            return 0.3
        return 1.0 if any(f.tonnes for f in forms) else 0.6

    def score_all(self, profile, diagnoses: dict, element: str = PRIMARY_ELEMENT):
        rec_by = {cl.size_class: self._rec_total(cl, element) for cl in profile.classes}
        total_rec = sum(rec_by.values()) or 1.0
        out = {}
        for cl in profile.classes:
            diag = diagnoses.get(cl.size_class)
            rec = {el: cl.recoverable_tonnes(el) for el in ELEMENT_SYMBOLS}  # оба — для контекста
            impact = rec_by[cl.size_class] / total_rec
            ctot = self._class_total(cl, element)
            addressability = (rec_by[cl.size_class] / ctot) if ctot else 0.0
            feas = 1.0 if (diag and not diag.needs_equipment) else 0.6
            conf = self.confidence(cl, element)
            adr = min(addressability, 1.0)
            clr = self._clarity(cl, element)
            # Приоритет ВЕДЁТ масштаб (impact — ФАКТ из данных: доля извлекаемых потерь).
            # Остальное — модификаторы (наша эвристика, НЕ факт; формула объяснена в
            # глоссарии): addressability и clarity — мягко (не переворачивают порядок),
            # feasibility/confidence — множители. clarity включена, т.к. один чёткий
            # механизм = понятнее и защитимее гипотеза (даёт «буст в понимании»).
            priority = impact * (0.5 + 0.5 * adr) * (0.7 + 0.3 * clr) * feas * conf
            out[cl.size_class] = Metrics(
                rec_tonnes=rec, impact=impact, addressability=adr,
                clarity=self._clarity(cl, element), confidence=conf, feasibility=feas,
                priority=round(priority, 5))
        return out
