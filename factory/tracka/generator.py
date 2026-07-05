from __future__ import annotations

from dataclasses import dataclass, field

from factory.config import SECONDARY_MIN_SHARE
from factory.tracka.intent import Intent, constraint_violations, parse_intent
from factory.tracka.metrics import Scorer
from factory.tracka.reader import ELEMENT_SYMBOLS
from factory.tracka.roadmap import build_roadmap
from factory.tracka.rules import diagnose


@dataclass
class Hypothesis:
    size_class: str
    family: str
    intervention: str
    alternatives: list
    dominant_form: str
    diagnosis: str
    target_element: str
    statement_if: str
    statement_then: str
    statement_because: str
    exp_test: str
    exp_metric: str
    exp_criterion: str
    evidence: list
    sources: list
    violates_constraints: list = field(default_factory=list)
    world_practice: str | None = None
    dossier: list = field(default_factory=list)
    roadmap: list = field(default_factory=list)
    secondary: bool = False
    literature: list = field(default_factory=list)
    expert_feedback: dict | None = None
    metrics: dict = field(default_factory=dict)
    rank: int = 0

class HypothesisGenerator:
    def __init__(self, scorer: Scorer | None = None):
        self.scorer = scorer or Scorer()

    def generate(self, profile, kpi: str = "", breadth: float = 0.0,
                 max_hyps: int = 0, log=lambda *a: None) -> list:
        intent = parse_intent(kpi)

        elements = (list(ELEMENT_SYMBOLS)
                    if (not intent.element_detected and intent.element_in_schema)
                    else [intent.target_element])
        hyps = []
        for element in elements:
            hyps.extend(self._for_element(profile, element, intent, breadth, log))

        hyps.sort(key=lambda h: -h.metrics["priority"])
        if max_hyps and max_hyps > 0:
            hyps = hyps[:max_hyps]
        for i, h in enumerate(hyps, 1):
            h.rank = i
            for e in h.evidence:
                e["source"] = profile.source
                e["path"] = profile.path
        return hyps

    def _for_element(self, profile, element, intent, breadth=0.0,
                     log=lambda *a: None) -> list:
        diagnoses = {cl.size_class: diagnose(cl.dominant_recoverable_form(element),
                                             cl.size_class)
                     for cl in profile.classes}
        metrics = self.scorer.score_all(profile, diagnoses, element=element)
        out = []
        for cl in profile.classes:
            diag = diagnoses.get(cl.size_class)
            if diag is None:
                log(f"[{element}] класс {cl.size_class}: пропущен — нет извлекаемой формы")
                continue
            if sum(metrics[cl.size_class].rec_tonnes.values()) <= 0:
                log(f"[{element}] класс {cl.size_class}: пропущен — нулевой извлекаемый тоннаж")
                continue

            n = 1 + round(max(0.0, min(1.0, breadth)) * (len(diag.interventions) - 1))
            for idx in range(n):
                out.append(self._build(cl, diag, metrics[cl.size_class], element, intent, idx))

            sec = self._secondary(cl, diag, metrics[cl.size_class], element, intent)
            if sec is not None:
                out.append(sec)
        return out

    def _build(self, cl, diag, m, element, intent: Intent, idx: int = 0) -> Hypothesis:
        rec = m.rec_tonnes
        impact_pct = round(m.impact * 100)

        primary = diag.interventions[idx]
        others = [x for j, x in enumerate(diag.interventions) if j != idx]
        other = next((e for e in ELEMENT_SYMBOLS if e != element), None)
        tons = f"{rec.get(element, 0)} т {element}"
        if other:
            tons += f" (+{rec.get(other, 0)} т {other})"

        evidence = []
        for el in ELEMENT_SYMBOLS:
            if cl.cells.get(el):
                evidence.append({"label": f"потери {el} в классе {cl.size_class}",
                                 "cell": cl.cells[el], "source": None})

        dom = cl.dominant_recoverable_form(element)
        domf = next((f for f in cl.forms if f.form == dom and f.element == element), None)
        if domf:
            evidence.append({"label": f"форма «{dom}» ({round(domf.pct,1)}%)",
                             "cell": domf.cell, "source": None})

        violates = constraint_violations(intent, diag.family, diag.needs_equipment,
                                          text=primary)
        priority = m.priority * (0.1 if violates else 1.0) * (0.9 ** idx)

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
            alternatives=others, dominant_form=dom,
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

            roadmap=build_roadmap(diag.family, primary, cl.size_class, element))

    def _secondary(self, cl, primary_diag, m, element, intent: Intent) -> Hypothesis | None:
        rec_forms = sorted((f for f in cl.forms
                            if f.element == element and f.recoverable and f.tonnes),
                           key=lambda f: -f.tonnes)
        total = sum(f.tonnes for f in rec_forms)
        if primary_diag is None or total <= 0 or len(rec_forms) < 2:
            return None
        for f2 in rec_forms[1:]:
            share = f2.tonnes / total
            if share < SECONDARY_MIN_SHARE:
                break
            diag2 = diagnose(f2.form, cl.size_class)
            if diag2 is None or diag2.family == primary_diag.family:
                continue
            return self._build_secondary(cl, diag2, m, element, intent, f2, share)
        return None

    def _build_secondary(self, cl, diag2, m, element, intent: Intent,
                         f2, share: float) -> Hypothesis:
        primary = diag2.interventions[0]

        rec = {el: round(sum(f.tonnes for f in cl.forms
                             if f.form == f2.form and f.element == el and f.recoverable), 1)
               for el in ELEMENT_SYMBOLS}
        impact2 = m.impact * share
        clarity2 = round(share, 3)
        feas2 = 0.6 if diag2.needs_equipment else 1.0
        priority2 = impact2 * (0.5 + 0.5 * m.addressability) * (0.7 + 0.3 * clarity2) \
            * feas2 * m.confidence

        violates = constraint_violations(intent, diag2.family, diag2.needs_equipment,
                                          text=" ".join([primary] + diag2.interventions[1:]))
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
