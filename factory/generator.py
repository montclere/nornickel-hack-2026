# -*- coding: utf-8 -*-
"""Сборка гипотез из профиля потерь. ДЕТЕРМИНИРОВАННО (текст — шаблоном).

Гипотеза = диагноз класса крупности + вмешательство из правил + метрики из данных.
LLM здесь НЕ участвует: и логика, и базовый текст воспроизводимы. Опциональная
LLM-полировка формулировки — отдельный шаг (см. llm.py), не влияет на смысл/метрики.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from factory.metrics import Scorer
from factory.rules import diagnose


@dataclass
class Hypothesis:
    size_class: str
    family: str
    intervention: str            # основное вмешательство
    alternatives: list           # прочие вмешательства того же семейства
    dominant_form: str
    diagnosis: str               # механизм
    statement_if: str
    statement_then: str
    statement_because: str
    evidence: list               # [{"label","cell","source"}] — заземление до ячейки
    sources: list
    metrics: dict = field(default_factory=dict)
    rank: int = 0


class HypothesisGenerator:
    def __init__(self, scorer: Scorer | None = None):
        self.scorer = scorer or Scorer()

    def generate(self, profile) -> list:
        diagnoses = {cl.size_class: diagnose(cl.dominant_recoverable_form("Ni"),
                                             cl.size_class)
                     for cl in profile.classes}
        metrics = self.scorer.score_all(profile, diagnoses)

        hyps = []
        for cl in profile.classes:
            diag = diagnoses.get(cl.size_class)
            if diag is None or sum(metrics[cl.size_class].rec_tonnes.values()) <= 0:
                continue
            hyps.append(self._build(cl, diag, metrics[cl.size_class]))

        hyps.sort(key=lambda h: -h.metrics["priority"])
        for i, h in enumerate(hyps, 1):
            h.rank = i
        return hyps

    def _build(self, cl, diag, m) -> Hypothesis:
        rec = m.rec_tonnes
        impact_pct = round(m.impact * 100)
        primary = diag.interventions[0]
        tons = f"{rec.get('Ni',0)} т Ni + {rec.get('Cu',0)} т Cu"
        evidence = []
        for el in ("Ni", "Cu"):
            if cl.cells.get(el):
                evidence.append({"label": f"потери {el} в классе {cl.size_class}",
                                 "cell": cl.cells[el], "source": None})
        # ячейка минералогии доминирующей формы
        dom = cl.dominant_recoverable_form("Ni")
        domf = next((f for f in cl.forms if f.form == dom and f.element == "Ni"), None)
        if domf:
            evidence.append({"label": f"форма «{dom}» ({round(domf.pct,1)}%)",
                             "cell": domf.cell, "source": None})
        return Hypothesis(
            size_class=cl.size_class, family=diag.family, intervention=primary,
            alternatives=diag.interventions[1:], dominant_form=dom,
            diagnosis=diag.mechanism,
            statement_if=f"{primary} (целевой класс {cl.size_class})",
            statement_then=(f"снизятся потери извлекаемого металла в классе "
                            f"{cl.size_class} (~{tons}; это {impact_pct}% всех "
                            f"извлекаемых потерь фабрики)"),
            statement_because=(f"в классе {cl.size_class} {rec.get('Ni',0)} т "
                               f"извлекаемого Ni сидит преимущественно в форме "
                               f"«{dom}»; {diag.mechanism}"),
            evidence=evidence, sources=diag.sources, metrics=m.as_dict())
