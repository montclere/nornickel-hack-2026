"""Use-case: сборка графа знаний из триплетов + заморозка снапшота.

Триплеты → нормализация сущностей в канонические узлы → рёбра влияния. Провалы
(outcome="failure") выделяются отдельным узлом type="failure" с closure_reason, к
которому ведёт ребро от опробованного реагента/подхода — это кладбище для
анти-граблей и топливо для реанимации.

snapshot_id = хеш отсортированного множества триплетов (domain.compute_snapshot_id):
один и тот же вход → один и тот же снапшот → те же гипотезы.
"""

from __future__ import annotations

from app.service.domain.graph_ops import compute_snapshot_id
from app.service.entities import Edge, GraphSnapshot, Node, Triplet

_CLOSURE_MARKERS = ("закрыт", "провал", "failure", "отказ")


def _is_closure(text: str) -> bool:
    """Похоже ли имя на «закрытие направления/провал» (а не на реальную сущность)."""
    low = text.lower()
    return any(m in low for m in _CLOSURE_MARKERS)


def build_nodes_and_edges(triplets: list[Triplet], normalizer) -> tuple[list[Node], list[Edge]]:
    """Триплеты → (узлы, рёбра). Детерминированно: вход сортируется перед сборкой."""
    names: set[str] = set()
    for t in triplets:
        names.add(t.subject)
        if not _is_closure(t.object):
            names.add(t.object)
    norm = normalizer.normalize(names)
    nodes_by_id = {n.id: n for n in norm.nodes}
    node_of = norm.node_of

    edges: list[Edge] = []
    failures: dict[str, Node] = {}

    def _edge(src: str, dst: str, sign: str, t: Triplet) -> Edge:
        return Edge(
            source=src, target=dst, sign=sign, conditions=dict(t.conditions),
            doc_id=t.doc_id, evidence_quote=t.evidence_quote, year=t.year,
        )

    ordered = sorted(triplets, key=lambda x: (x.subject, x.relation, x.object, x.year, x.doc_id))
    for t in ordered:
        s_id = node_of.get(t.subject)
        if s_id is None:
            continue
        if t.outcome == "failure":
            f_id = f"failure_{t.doc_id}"
            if f_id not in failures:
                failures[f_id] = Node(
                    id=f_id, label=f"Провал: {nodes_by_id[s_id].label}",
                    type="failure", closure_reason=t.closure_reason,
                )
            elif t.closure_reason and not failures[f_id].closure_reason:
                failures[f_id].closure_reason = t.closure_reason
            edges.append(_edge(s_id, f_id, "-", t))  # реагент → провал
            if not _is_closure(t.object):
                o_id = node_of.get(t.object)
                if o_id:
                    edges.append(_edge(s_id, o_id, t.sign, t))  # + реальное влияние
        else:
            o_id = node_of.get(t.object)
            if o_id:
                edges.append(_edge(s_id, o_id, t.sign, t))

    all_nodes = sorted({**nodes_by_id, **failures}.values(), key=lambda n: n.id)
    return all_nodes, edges


class BuildGraph:
    """Собирает граф в репозиторий и возвращает замороженный снапшот."""

    def __init__(self, normalizer, graph_repository) -> None:
        self.normalizer = normalizer
        self.repo = graph_repository

    def execute(self, triplets: list[Triplet]) -> GraphSnapshot:
        nodes, edges = build_nodes_and_edges(triplets, self.normalizer)
        self.repo.add_nodes(nodes)
        self.repo.add_edges(edges)
        return GraphSnapshot(
            snapshot_id=compute_snapshot_id(triplets), triplet_count=len(triplets)
        )


__all__ = ["BuildGraph", "build_nodes_and_edges"]
