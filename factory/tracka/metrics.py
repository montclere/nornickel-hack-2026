from __future__ import annotations

from dataclasses import dataclass

from factory.tracka.reader import ELEMENT_SYMBOLS, PRIMARY_ELEMENT


@dataclass
class Metrics:
    rec_tonnes: dict
    impact: float
    addressability: float
    clarity: float
    confidence: float
    feasibility: float
    priority: float

    def as_dict(self):
        return {"rec_tonnes": {k: round(v, 1) for k, v in self.rec_tonnes.items()},
                "impact": round(self.impact, 3), "addressability": round(self.addressability, 3),
                "clarity": round(self.clarity, 3), "confidence": round(self.confidence, 2),
                "feasibility": round(self.feasibility, 2), "priority": round(self.priority, 4)}

class Scorer:

    def _rec_total(self, cl, element) -> float:
        return cl.recoverable_tonnes(element)

    def _class_total(self, cl, element) -> float:
        return cl.tonnes.get(element) or 0.0

    def _clarity(self, cl, element) -> float:
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
            rec = {el: cl.recoverable_tonnes(el) for el in ELEMENT_SYMBOLS}
            impact = rec_by[cl.size_class] / total_rec
            ctot = self._class_total(cl, element)
            addressability = (rec_by[cl.size_class] / ctot) if ctot else 0.0
            feas = 1.0 if (diag and not diag.needs_equipment) else 0.6
            conf = self.confidence(cl, element)
            adr = min(addressability, 1.0)
            clr = self._clarity(cl, element)

            priority = impact * (0.5 + 0.5 * adr) * (0.7 + 0.3 * clr) * feas * conf
            out[cl.size_class] = Metrics(
                rec_tonnes=rec, impact=impact, addressability=adr,
                clarity=self._clarity(cl, element), confidence=conf, feasibility=feas,
                priority=round(priority, 5))
        return out
