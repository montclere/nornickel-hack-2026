# -*- coding: utf-8 -*-
"""Канонический граф знаний из извлечённых связей. Провенанс + метаданные.

Единое представление независимо от источника (текст или таблица). Узлы —
нормализованные сущности; рёбра — связи со знаком, цитатой, источником, датой.
Дальнейшее рассуждение (пробелы, новизна, ранг) — детерминированно поверх графа.
"""
from __future__ import annotations

import re

import networkx as nx


def _norm_entity(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


class KnowledgeGraph:
    def __init__(self, relations):
        self.g = nx.MultiDiGraph()
        for r in relations:
            self.add(r)

    def add(self, r):
        a, b = _norm_entity(r["subject"]), _norm_entity(r["object"])
        if not a or not b:
            return
        for node, label in ((a, r["subject"]), (b, r["object"])):
            if node not in self.g:
                self.g.add_node(node, label=label.strip())
        self.g.add_edge(a, b, sign=r.get("sign", 0), relation=r.get("relation", "связан"),
                        quote=r.get("quote", ""), source=r.get("source", ""),
                        locator=r.get("locator", ""), meta=r.get("meta", {}))

    def stats(self):
        return {"nodes": self.g.number_of_nodes(), "edges": self.g.number_of_edges()}

    def label(self, node):
        return self.g.nodes[node].get("label", node)

    def out_edges(self, node):
        return [(v, d) for _, v, d in self.g.out_edges(node, data=True)]

    def in_degree(self, node):
        return self.g.in_degree(node)

    def nodes(self):
        return list(self.g.nodes)

    def to_layered(self, max_nodes=40):
        """Упрощённая сериализация для визуализации (топ-узлы по связности)."""
        deg = sorted(self.g.degree, key=lambda x: -x[1])[:max_nodes]
        keep = {n for n, _ in deg}
        nodes = [{"id": n, "label": self.label(n), "deg": self.g.degree(n)} for n in keep]
        edges = [{"src": u, "dst": v, "sign": d.get("sign", 0)}
                 for u, v, d in self.g.edges(data=True) if u in keep and v in keep]
        return {"nodes": nodes, "edges": edges}
