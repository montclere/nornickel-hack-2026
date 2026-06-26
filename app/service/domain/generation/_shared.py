"""Общие детерминированные хелперы генераторов гипотез.

Чистый домен: только сущности и порт `GraphRepository`. Никаких импортов из
`app.infrastructure` / `app.api`.
"""

from __future__ import annotations

from app.service.domain.graph_ops import resolve_kpi_node
from app.service.entities import Edge, Hypothesis
from app.service.interfaces import GraphRepository

# порядок происхождения для детерминированной сортировки оркестратора
ORIGIN_ORDER: dict[str, int] = {"gap": 0, "reanimation": 1, "contradiction": 2}


def label(repo: GraphRepository, node_id: str) -> str:
    """Человекочитаемая метка узла (или сам id, если узла нет)."""
    node = repo.get_node(node_id)
    return node.label if node is not None else node_id


def sources_from_edges(edges: list[Edge]) -> list[str]:
    """Отсортированные уникальные doc_id из рёбер-доказательств."""
    return sorted({e.doc_id for e in edges if e.doc_id})


def involved_node_ids(hypothesis: Hypothesis) -> set[str]:
    """Все узлы, упомянутые в цепочке доказательств гипотезы."""
    ids: set[str] = set()
    for edge in hypothesis.evidence_path:
        ids.add(edge.source)
        ids.add(edge.target)
    return ids


__all__ = [
    "ORIGIN_ORDER",
    "label",
    "sources_from_edges",
    "involved_node_ids",
    "resolve_kpi_node",
]
