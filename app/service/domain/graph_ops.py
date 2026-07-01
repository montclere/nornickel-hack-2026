"""Чистые запросы над графом (пути, конфликты, соседи) + хеш снапшота.

Это тонкая прослойка домена над портом `GraphRepository`: вся работа с графом
идёт через интерфейс, поэтому функции остаются независимыми от реализации
(NetworkX/Neo4j) и детерминированными.
"""

from __future__ import annotations

import hashlib
import json

from app.service.entities import Edge, Node, Triplet
from app.service.interfaces import GraphRepository


def find_paths(
    repo: GraphRepository, source: str, target: str, max_len: int = 3
) -> list[list[Edge]]:
    """Все направленные пути source→target длиной ≤ max_len (цепочки доказательств)."""
    return repo.query_paths(source, target, max_len)


def find_neighbors(repo: GraphRepository, node_id: str) -> list[Node]:
    """Соседи узла."""
    return repo.neighbors(node_id)


def find_conflicts(repo: GraphRepository) -> list[tuple[Edge, Edge]]:
    """Пары конфликтующих рёбер (один source→target, противоположный знак)."""
    return repo.conflicting_edges()


def find_failures(repo: GraphRepository) -> list[Node]:
    """Узлы-провалы (кладбище) с причинами закрытия."""
    return repo.failure_nodes()


def resolve_kpi_node(repo: GraphRepository, kpi: str) -> str | None:
    """Сопоставить строку KPI с id узла-KPI в графе.

    Принимает и канонический id ("Ni_recovery"), и человекочитаемый запрос
    ("извлечение Ni +2%"): матч по id → по label/alias → единственный KPI-узел.
    """
    direct = repo.get_node(kpi)
    if direct is not None and direct.type == "KPI":
        return direct.id
    kpis = sorted((n for n in repo.all_nodes() if n.type == "KPI"), key=lambda n: n.id)
    low = kpi.lower()
    for node in kpis:
        names = [node.label.lower(), *(a.lower() for a in node.aliases)]
        if any(name and (name in low or low in name) for name in names):
            return node.id
    return kpis[0].id if len(kpis) == 1 else None


def compute_snapshot_id(triplets: list[Triplet]) -> str:
    """Стабильный хеш отсортированного множества триплетов.

    Один и тот же набор фактов → один и тот же snapshot_id, в любом порядке.
    Это якорь воспроизводимости: генерация идёт ПОВЕРХ снапшота.
    """
    keys = sorted(
        (t.subject, t.relation, t.object, t.sign, t.year, t.doc_id) for t in triplets
    )
    blob = json.dumps(keys, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def graph_snapshot_id(repo: GraphRepository) -> str:
    """Стабильный хеш текущего состояния графа (по рёбрам).

    Используется после сборки/дозаполнения: добавил факты в граф → новый
    snapshot_id. Тот же набор рёбер → тот же id, поэтому генерация воспроизводима.
    """
    keys = sorted(
        (e.source, e.target, e.sign, e.year, e.doc_id) for e in repo.all_edges()
    )
    blob = json.dumps(keys, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "find_paths",
    "find_neighbors",
    "find_conflicts",
    "find_failures",
    "resolve_kpi_node",
    "compute_snapshot_id",
    "graph_snapshot_id",
]
