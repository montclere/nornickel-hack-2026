"""Граф знаний на NetworkX MultiDiGraph (реализация порта GraphRepository).

MultiDiGraph хранит параллельные рёбра между одной парой узлов — это нужно
генератору противоречий (один source→target с разным знаком в разные годы).
Каждое ребро несёт sign, conditions, doc_id, evidence_quote, year.

networkx импортируется лениво, чтобы fake-режим работал без этой зависимости.
save/load пишут тот же JSON-формат, что и FakeGraphRepository — реализации
взаимозаменяемы, домен ходит в граф только через интерфейс.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.service.entities import Edge, Node


class NetworkxGraphRepository:
    """GraphRepository поверх nx.MultiDiGraph."""

    def __init__(self) -> None:
        import networkx as nx  # ленивый импорт

        self._g = nx.MultiDiGraph()

    # --- запись ---

    def add_nodes(self, nodes: list[Node]) -> None:
        for n in nodes:
            self._g.add_node(
                n.id,
                label=n.label,
                type=n.type,
                aliases=list(n.aliases),
                closure_reason=n.closure_reason,
            )

    def add_edges(self, edges: list[Edge]) -> None:
        for e in edges:
            # узлы-«висяки» создаём, чтобы граф не терял рёбра на неполных данных
            for nid in (e.source, e.target):
                if nid not in self._g:
                    self._g.add_node(nid, label=nid, type="material", aliases=[], closure_reason=None)
            self._g.add_edge(
                e.source, e.target,
                sign=e.sign, conditions=dict(e.conditions), doc_id=e.doc_id,
                evidence_quote=e.evidence_quote, year=e.year,
            )

    # --- чтение узлов ---

    def _node(self, nid: str) -> Node:
        d = self._g.nodes[nid]
        return Node(
            id=nid,
            label=d.get("label", nid),
            type=d.get("type", "material"),
            aliases=list(d.get("aliases", [])),
            closure_reason=d.get("closure_reason"),
        )

    def get_node(self, node_id: str) -> Node | None:
        return self._node(node_id) if node_id in self._g else None

    def all_nodes(self) -> list[Node]:
        return [self._node(nid) for nid in sorted(self._g.nodes)]

    def failure_nodes(self) -> list[Node]:
        return [
            self._node(nid)
            for nid in sorted(self._g.nodes)
            if self._g.nodes[nid].get("type") == "failure"
        ]

    def neighbors(self, node_id: str) -> list[Node]:
        if node_id not in self._g:
            return []
        ids = set(self._g.successors(node_id)) | set(self._g.predecessors(node_id))
        return [self._node(nid) for nid in sorted(ids)]

    # --- чтение рёбер ---

    @staticmethod
    def _edge(u: str, v: str, data: dict) -> Edge:
        return Edge(
            source=u, target=v,
            sign=data.get("sign", "0"), conditions=dict(data.get("conditions", {})),
            doc_id=data.get("doc_id", ""), evidence_quote=data.get("evidence_quote", ""),
            year=data.get("year", 0),
        )

    def all_edges(self) -> list[Edge]:
        edges = [self._edge(u, v, d) for u, v, d in self._g.edges(data=True)]
        edges.sort(key=lambda e: (e.source, e.target, e.year, e.sign, e.doc_id))
        return edges

    def out_edges(self, node_id: str) -> list[Edge]:
        if node_id not in self._g:
            return []
        return [self._edge(u, v, d) for u, v, d in self._g.out_edges(node_id, data=True)]

    def in_edges(self, node_id: str) -> list[Edge]:
        if node_id not in self._g:
            return []
        return [self._edge(u, v, d) for u, v, d in self._g.in_edges(node_id, data=True)]

    # --- запросы ---

    def query_paths(self, source: str, target: str, max_len: int = 3) -> list[list[Edge]]:
        """Все простые направленные пути source→target длиной ≤ max_len."""
        import networkx as nx

        if source not in self._g or target not in self._g:
            return []
        paths: list[list[Edge]] = []
        for edge_path in nx.all_simple_edge_paths(self._g, source, target, cutoff=max_len):
            chain = [self._edge(u, v, self._g.edges[u, v, k]) for u, v, k in edge_path]
            paths.append(chain)
        # детерминированный порядок: по последовательности (source, target, year)
        paths.sort(key=lambda ch: [(e.source, e.target, e.year) for e in ch])
        return paths

    def conflicting_edges(self) -> list[tuple[Edge, Edge]]:
        """Пары рёбер один source→target с противоположным знаком (нужны для противоречий)."""
        by_pair: dict[tuple[str, str], list[Edge]] = {}
        for u, v, d in self._g.edges(data=True):
            by_pair.setdefault((u, v), []).append(self._edge(u, v, d))
        out: list[tuple[Edge, Edge]] = []
        for edges in by_pair.values():
            edges.sort(key=lambda e: (e.year, e.sign, e.doc_id))
            for i in range(len(edges)):
                for j in range(i + 1, len(edges)):
                    a, b = edges[i], edges[j]
                    if a.sign != b.sign and "0" not in (a.sign, b.sign):
                        out.append((a, b))
        return out

    # --- персист (JSON, тот же формат, что у FakeGraphRepository) ---

    def save(self, path: str | Path) -> None:
        nodes = sorted((self._node(nid).model_dump() for nid in self._g.nodes), key=lambda n: n["id"])
        edges = sorted(
            (self._edge(u, v, d).model_dump() for u, v, d in self._g.edges(data=True)),
            key=lambda e: (e["source"], e["target"], e["year"], e["sign"], e["doc_id"]),
        )
        Path(path).write_text(
            json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, path: str | Path) -> None:
        import networkx as nx

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self._g = nx.MultiDiGraph()
        self.add_nodes([Node(**n) for n in payload.get("nodes", [])])
        self.add_edges([Edge(**e) for e in payload.get("edges", [])])


__all__ = ["NetworkxGraphRepository"]
