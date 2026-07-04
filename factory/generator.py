# -*- coding: utf-8 -*-
"""Сборка гипотез из профиля потерь. ДЕТЕРМИНИРОВАННО (текст — шаблоном).

Гипотеза = диагноз класса крупности (по ЦЕЛЕВОМУ элементу из KPI, см. intent.py) +
вмешательство из правил + метрики из данных. LLM здесь НЕ участвует: и логика, и
базовый текст воспроизводимы. Опциональная LLM-полировка формулировки — отдельный
шаг (см. llm.py), не влияет на смысл/метрики.

world_practice (мировые практики / подтверждено внедрением) — сюда садится будущий
модуль веб-поиска (не сегодня): проверяет, применялось ли вмешательство где-то ещё, и
приносит внешнюю цитату. Пока — явный None, а не выдумка.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from factory.intent import Intent, parse_intent
from factory.metrics import Scorer
from factory.reader import ELEMENT_SYMBOLS
from factory.rules import diagnose


@dataclass
class Hypothesis:
    size_class: str
    family: str
    intervention: str            # основное вмешательство
    alternatives: list           # прочие вмешательства того же семейства
    dominant_form: str
    diagnosis: str               # механизм
    target_element: str          # элемент, под который оптимизирован диагноз (из KPI)
    statement_if: str
    statement_then: str
    statement_because: str
    experiment: str              # протокол проверки — детерминированный шаблон
    evidence: list                # [{"label","cell","source"}] — заземление до ячейки
    sources: list
    violates_constraints: list = field(default_factory=list)  # ограничения из промпта, которые нарушены
    world_practice: str | None = None   # TODO(веб-поиск): подтверждение внедрения в мировой практике
    expert_feedback: dict | None = None  # вердикт эксперта из feedback.json (см. feedback.py)
    metrics: dict = field(default_factory=dict)
    rank: int = 0


class HypothesisGenerator:
    def __init__(self, scorer: Scorer | None = None):
        self.scorer = scorer or Scorer()

    def generate(self, profile, kpi: str = "", log=lambda *a: None) -> list:
        intent = parse_intent(kpi)
        element = intent.target_element
        diagnoses = {cl.size_class: diagnose(cl.dominant_recoverable_form(element),
                                             cl.size_class)
                     for cl in profile.classes}
        metrics = self.scorer.score_all(profile, diagnoses, element=element)

        hyps = []
        for cl in profile.classes:
            diag = diagnoses.get(cl.size_class)
            # НЕ молчим: если класс не даёт гипотезы — честно говорим почему (нет
            # извлекаемой формы вовсе / нулевой извлекаемый тоннаж по целевому элементу)
            if diag is None:
                log(f"класс {cl.size_class}: пропущен — нет извлекаемой формы {element} "
                    f"(дом. форма отсутствует/неизвлекаема)")
                continue
            if sum(metrics[cl.size_class].rec_tonnes.values()) <= 0:
                log(f"класс {cl.size_class}: пропущен — нулевой извлекаемый тоннаж {element}")
                continue
            hyps.append(self._build(cl, diag, metrics[cl.size_class], element, intent))

        hyps.sort(key=lambda h: -h.metrics["priority"])
        for i, h in enumerate(hyps, 1):
            h.rank = i
        return hyps

    def _build(self, cl, diag, m, element, intent: Intent) -> Hypothesis:
        rec = m.rec_tonnes
        impact_pct = round(m.impact * 100)
        primary = diag.interventions[0]
        other = next((e for e in ELEMENT_SYMBOLS if e != element), None)
        tons = f"{rec.get(element, 0)} т {element}"
        if other:
            tons += f" (+{rec.get(other, 0)} т {other})"

        evidence = []
        for el in ELEMENT_SYMBOLS:
            if cl.cells.get(el):
                evidence.append({"label": f"потери {el} в классе {cl.size_class}",
                                 "cell": cl.cells[el], "source": None})
        # ячейка минералогии доминирующей формы (по целевому элементу)
        dom = cl.dominant_recoverable_form(element)
        domf = next((f for f in cl.forms if f.form == dom and f.element == element), None)
        if domf:
            evidence.append({"label": f"форма «{dom}» ({round(domf.pct,1)}%)",
                             "cell": domf.cell, "source": None})

        # ограничения из промпта: если запрет на новое оборудование, а вмешательство
        # его требует — не скрываем гипотезу, а честно помечаем и штрафуем приоритет
        violates = []
        priority = m.priority
        if intent.no_new_equipment and diag.needs_equipment:
            violates.append("без нового оборудования")
            priority *= 0.1

        experiment = (f"Тест на классе {cl.size_class}: применить «{primary}» "
                     f"(промышленный масштаб), замерить извлечение {element} "
                     f"до/после при контролируемых условиях, сравнить с базовым "
                     f"режимом. Критерий успеха — рост извлечения {element} из "
                     f"класса {cl.size_class} относительно базовой линии.")

        m_dict = m.as_dict()
        m_dict["priority"] = round(priority, 5)

        return Hypothesis(
            size_class=cl.size_class, family=diag.family, intervention=primary,
            alternatives=diag.interventions[1:], dominant_form=dom,
            diagnosis=diag.mechanism, target_element=element,
            statement_if=f"{primary} (целевой класс {cl.size_class})",
            statement_then=(f"снизятся потери извлекаемого {element} в классе "
                            f"{cl.size_class} (~{tons}; это {impact_pct}% всех "
                            f"извлекаемых потерь {element} по фабрике)"),
            statement_because=(f"в классе {cl.size_class} {rec.get(element, 0)} т "
                               f"извлекаемого {element} сидит преимущественно в форме "
                               f"«{dom}»; {diag.mechanism}"),
            experiment=experiment, evidence=evidence, sources=diag.sources,
            violates_constraints=violates, metrics=m_dict)
