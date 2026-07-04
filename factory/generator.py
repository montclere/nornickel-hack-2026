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

from factory.config import SECONDARY_MIN_SHARE
from factory.intent import Intent, constraint_violations, parse_intent
from factory.metrics import Scorer
from factory.reader import ELEMENT_SYMBOLS
from factory.roadmap import build_roadmap
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
    exp_test: str                # эксперимент: ЧТО делаем
    exp_metric: str              # эксперимент: ЧТО замеряем
    exp_criterion: str           # эксперимент: критерий успеха
    evidence: list                # [{"label","cell","source"}] — заземление до ячейки
    sources: list
    violates_constraints: list = field(default_factory=list)  # ограничения из промпта, которые нарушены
    world_practice: str | None = None   # веб-поиск: подтверждение внедрения (websearch.py)
    dossier: list = field(default_factory=list)  # OpenAlex: реальные источники (openalex.py)
    roadmap: list = field(default_factory=list)  # лаборатория→пилот→внедрение с критериями (roadmap.py)
    secondary: bool = False       # второе направление класса (по НЕдоминирующей форме)
    literature: list = field(default_factory=list)  # цитаты из выданного корпуса (litsupport.py)
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
            # второе направление класса: заметная НЕдоминирующая форма → своя гипотеза.
            # Пример: доминирует закрытый (диагноз «доизмельчение»), но 30% извлекаемого
            # сидит в раскрытой форме — флотационное направление честно предлагается
            # тоже, с тоннажом и приоритетом, промасштабированными на долю формы.
            sec = self._secondary(cl, diag, metrics[cl.size_class], element, intent)
            if sec is not None:
                hyps.append(sec)

        hyps.sort(key=lambda h: -h.metrics["priority"])
        for i, h in enumerate(hyps, 1):
            h.rank = i
            for e in h.evidence:                 # реальный файл-источник к каждой ячейке
                e["source"] = profile.source
                e["path"] = profile.path         # полный путь → кликабельная ссылка в отчёте
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

        # ограничения из промпта: гипотеза, конфликтующая с запретом (оборудование/
        # реагенты), не скрывается — честно помечается и штрафуется по приоритету
        violates = constraint_violations(intent, diag.family, diag.needs_equipment)
        priority = m.priority * (0.1 if violates else 1.0)

        exp_test = (f"Применить «{primary}» на классе {cl.size_class} в промышленном "
                    f"масштабе при контролируемых условиях, сравнить с базовым режимом.")
        exp_metric = (f"Извлечение {element} из класса {cl.size_class} до/после "
                      f"(и содержание {element} в хвостах этого класса).")
        exp_criterion = (f"Рост извлечения {element} из класса {cl.size_class} относительно "
                         f"базовой линии без ухудшения качества концентрата.")

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
            exp_test=exp_test, exp_metric=exp_metric, exp_criterion=exp_criterion,
            evidence=evidence, sources=diag.sources,
            violates_constraints=violates, metrics=m_dict,
            # дорожная карта: лаборатория → пилот → внедрение, с критериями перехода
            roadmap=build_roadmap(diag.family, primary, cl.size_class, element))

    def _secondary(self, cl, primary_diag, m, element, intent: Intent) -> Hypothesis | None:
        """Гипотеза по ВТОРОЙ извлекаемой форме класса, если её доля извлекаемого
        тоннажа ≥ SECONDARY_MIN_SHARE и диагноз даёт ДРУГОЕ семейство вмешательства.

        Физика: класс редко теряет металл по одному механизму — при доминирующем
        закрытом минерале раскрытая доля всё равно недофлотирована (и наоборот).
        Раньше генерировался только диагноз доминирующей формы → целые семейства
        (флотация/реагенты) выпадали из выдачи на фабриках, где закрытая форма
        доминирует во всех классах (см. промахи golden-бенчмарка на НОФ)."""
        rec_forms = sorted((f for f in cl.forms
                            if f.element == element and f.recoverable and f.tonnes),
                           key=lambda f: -f.tonnes)
        total = sum(f.tonnes for f in rec_forms)
        if primary_diag is None or total <= 0 or len(rec_forms) < 2:
            return None
        for f2 in rec_forms[1:]:
            share = f2.tonnes / total
            if share < SECONDARY_MIN_SHARE:
                break                       # формы по убыванию — дальше только меньше
            diag2 = diagnose(f2.form, cl.size_class)
            if diag2 is None or diag2.family == primary_diag.family:
                continue
            return self._build_secondary(cl, diag2, m, element, intent, f2, share)
        return None

    def _build_secondary(self, cl, diag2, m, element, intent: Intent,
                         f2, share: float) -> Hypothesis:
        """Карточка второго направления: числа промасштабированы на долю формы,
        приоритет — той же формулой, что в metrics.py (масштаб ведёт)."""
        primary = diag2.interventions[0]
        # тоннаж ИМЕННО этой формы по каждому элементу (не всего класса)
        rec = {el: round(sum(f.tonnes for f in cl.forms
                             if f.form == f2.form and f.element == el and f.recoverable), 1)
               for el in ELEMENT_SYMBOLS}
        impact2 = m.impact * share
        clarity2 = round(share, 3)
        feas2 = 0.6 if diag2.needs_equipment else 1.0
        priority2 = impact2 * (0.5 + 0.5 * m.addressability) * (0.7 + 0.3 * clarity2) \
            * feas2 * m.confidence

        violates = constraint_violations(intent, diag2.family, diag2.needs_equipment)
        if violates:
            priority2 *= 0.1

        evidence = [{"label": f"потери {el} в классе {cl.size_class}",
                     "cell": cl.cells[el], "source": None}
                    for el in ELEMENT_SYMBOLS if cl.cells.get(el)]
        evidence.append({"label": f"форма «{f2.form}» ({round(f2.pct, 1)}%)",
                         "cell": f2.cell, "source": None})

        dom = cl.dominant_recoverable_form(element)
        other = next((e for e in ELEMENT_SYMBOLS if e != element), None)
        tons = f"{rec.get(element, 0)} т {element}"
        if other and rec.get(other):
            tons += f" (+{rec.get(other, 0)} т {other})"

        return Hypothesis(
            size_class=cl.size_class, family=diag2.family, intervention=primary,
            alternatives=diag2.interventions[1:], dominant_form=f2.form,
            diagnosis=diag2.mechanism, target_element=element, secondary=True,
            statement_if=f"{primary} (целевой класс {cl.size_class}, второе направление)",
            statement_then=(f"снизятся потери извлекаемого {element} в классе "
                            f"{cl.size_class} в форме «{f2.form}» (~{tons}; "
                            f"{round(share * 100)}% извлекаемого в классе, "
                            f"{round(impact2 * 100)}% потерь {element} по фабрике)"),
            statement_because=(f"помимо доминирующей формы «{dom}», в классе "
                               f"{cl.size_class} {rec.get(element, 0)} т извлекаемого "
                               f"{element} в форме «{f2.form}»; {diag2.mechanism}"),
            exp_test=(f"Применить «{primary}» на классе {cl.size_class} (второе "
                      f"направление) в промышленном масштабе, сравнить с базовым режимом."),
            exp_metric=(f"Извлечение {element} из класса {cl.size_class} в форме "
                        f"«{f2.form}» до/после."),
            exp_criterion=(f"Рост извлечения {element} из класса {cl.size_class} "
                           f"относительно базовой линии без ухудшения качества концентрата."),
            evidence=evidence, sources=diag2.sources, violates_constraints=violates,
            metrics={"rec_tonnes": rec, "impact": round(impact2, 3),
                     "addressability": round(m.addressability, 3), "clarity": clarity2,
                     "confidence": round(m.confidence, 2), "feasibility": feas2,
                     "priority": round(priority2, 5)},
            roadmap=build_roadmap(diag2.family, primary, cl.size_class, element))
