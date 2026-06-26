"""Фильтр «АНТИ-ГРАБЛИ» — чистый домен.

Каждый кандидат сверяется с узлами-провалами; при пересечении заполняется
graveyard_check (warning, report_ref, reason, чем гипотеза отличается). Фильтр не
выбрасывает кандидата — он помечает его предупреждением для эксперта.
"""

from __future__ import annotations

from app.service.domain.generation import _shared
from app.service.entities import Edge, GraveyardCheck, Hypothesis, Node
from app.service.interfaces import GraphRepository


def apply(repo: GraphRepository, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Проставить graveyard_check каждому кандидату (новый список, без мутаций)."""
    failures = [
        (failure, *_subject(repo, failure))
        for failure in sorted(repo.failure_nodes(), key=lambda n: n.id)
    ]
    return [
        h.model_copy(update={"graveyard_check": _check(h, failures)}) for h in hypotheses
    ]


def _subject(repo: GraphRepository, failure: Node) -> tuple[str | None, Edge | None]:
    ins = sorted(repo.in_edges(failure.id), key=lambda e: (e.source, e.year, e.doc_id))
    return (ins[0].source, ins[0]) if ins else (None, None)


def _check(
    hypothesis: Hypothesis, failures: list[tuple[Node, str | None, Edge | None]]
) -> GraveyardCheck:
    involved = _shared.involved_node_ids(hypothesis)
    for failure, subject_id, link in failures:
        hit = failure.id in involved or (subject_id is not None and subject_id in involved)
        if not hit:
            continue
        if hypothesis.origin == "reanimation":
            difference = "гипотеза адресует это закрытие: свежий факт снимает причину"
        else:
            difference = (
                "пересекается с закрытым направлением — проверьте, чем гипотеза отличается"
            )
        return GraveyardCheck(
            warning=True,
            report_ref=link.doc_id if link else None,
            reason=failure.closure_reason,
            difference=difference,
        )
    return GraveyardCheck()  # пересечений с кладбищем нет


__all__ = ["apply"]
