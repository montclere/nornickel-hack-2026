"""Генератор РЕАНИМАЦИИ ИЗ КЛАДБИЩА — чистый домен.

Для узла-провала берётся closure_reason; ищется свежий факт (год > года провала),
снимающий причину. Кандидат несёт ссылки на отчёт-провал и на свежий факт.
"""

from __future__ import annotations

from app.service.domain.generation import _shared
from app.service.entities import Edge, ExperimentProtocol, Hypothesis, Node
from app.service.interfaces import GraphRepository

ORIGIN = "reanimation"

# семейство причины (подстрока) → ключевые слова свежего факта, её снимающего
_LIFT_FAMILIES: list[tuple[str, list[str]]] = [
    ("дорог", ["дешев", "дёшев", "дешёв", "удешев", "снижает стоимость", "снижение стоимости",
               "low-cost", "low cost", "cheap", "cheaper", "reduces reagent cost",
               "reduces cost", "cost reduction"]),
    ("стоим", ["дешев", "дёшев", "дешёв", "удешев", "снижает стоимость", "low-cost", "cheaper"]),
    ("оборудован", ["новая методика", "новый метод", "доступн", "настольн", "компактн",
                    "new method", "portable", "compact", "без специального оборудования"]),
    ("норматив", ["изменён норматив", "изменены нормативы", "новый норматив", "новый стандарт",
                  "регламент обновл", "updated regulation", "regulation change"]),
    ("стандарт", ["новый стандарт", "обновлён стандарт", "регламент обновл", "updated standard"]),
    ("эффект", ["повышает", "увеличивает", "improves", "increase"]),  # «нет эффекта»
]


def _lift_keywords(reason: str) -> list[str]:
    """Ключевые слова свежего факта, снимающего причину закрытия."""
    low = reason.lower()
    for needle, keywords in _LIFT_FAMILIES:
        if needle in low:
            return keywords
    return []  # неизвестная причина → консервативно не реанимируем


def generate(repo: GraphRepository, kpi: str | None = None) -> list[Hypothesis]:
    out: list[Hypothesis] = []
    for failure in sorted(repo.failure_nodes(), key=lambda n: n.id):
        if not failure.closure_reason:
            continue
        subject_id, link = _failure_subject(repo, failure)
        if subject_id is None or link is None:
            continue
        keywords = _lift_keywords(failure.closure_reason)
        if not keywords:
            continue
        fresh = _find_fresh_fact(repo, subject_id, link.year, keywords)
        if fresh is None:
            continue
        out.append(_build(repo, failure, subject_id, link, fresh, kpi))
    return out


def _failure_subject(repo: GraphRepository, failure: Node) -> tuple[str | None, Edge | None]:
    """Субъект провала и ребро-привязка: первое входящее ребро subject→failure."""
    ins = sorted(repo.in_edges(failure.id), key=lambda e: (e.source, e.year, e.doc_id))
    if ins:
        return ins[0].source, ins[0]
    return None, None


def _find_fresh_fact(
    repo: GraphRepository, subject_id: str, failure_year: int, keywords: list[str]
) -> Edge | None:
    """Свежее ребро про субъект (год > года провала), снимающее причину."""
    matches: list[Edge] = []
    for edge in repo.all_edges():
        if edge.year <= failure_year:
            continue
        if subject_id not in (edge.source, edge.target):
            continue
        quote = edge.evidence_quote.lower()
        if any(k in quote for k in keywords):
            matches.append(edge)
    matches.sort(key=lambda e: (e.year, e.doc_id, e.source, e.target))
    return matches[0] if matches else None


def _build(
    repo: GraphRepository, failure: Node, subject_id: str, link: Edge, fresh: Edge,
    kpi: str | None,
) -> Hypothesis:
    subj = _shared.label(repo, subject_id)
    reason = failure.closure_reason
    target = _shared.label(repo, kpi) if kpi else "целевой KPI"
    evidence = [link, fresh]
    return Hypothesis(
        id=f"h_reanim__{failure.id}",
        statement_if=f"вернуться к «{subj}»",
        statement_then=f"улучшится {target}",
        statement_because=(
            f"«{subj}» был закрыт по причине «{reason}» (год {link.year}), но свежий факт "
            f"{fresh.year} снимает её: {fresh.evidence_quote}"
        ),
        origin=ORIGIN,
        evidence_path=evidence,
        experiment_protocol=ExperimentProtocol(
            method=f"Повторное испытание «{subj}» с учётом свежего факта ({fresh.year})",
            equipment="Лабораторная флотомашина, ICP-OES",
            duration_days=45,
            cost_rub=1_500_000,
        ),
        sources=_shared.sources_from_edges(evidence),
    )


__all__ = ["generate", "ORIGIN"]
