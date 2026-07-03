# -*- coding: utf-8 -*-
"""Граф знаний из профиля потерь (networkx). ДЕТЕРМИНИРОВАННО.

Слои: Элемент → Класс крупности → Минеральная форма.
Рёбра несут тоннаж (ширина ребра на визуализации ∝ потерям). Извлекаемые формы
помечены. Граф — не чёрный ящик: любой узел/ребро читается прямо из отчёта.
"""
from __future__ import annotations

import networkx as nx

from factory.reader import ELEMENT_SYMBOLS, PRIMARY_ELEMENT, class_sort_key


class KnowledgeGraph:
    def __init__(self, profile):
        self.profile = profile
        self.g = nx.MultiDiGraph()
        self._build()

    def _build(self):
        p = self.profile
        for el in p.elements or dict.fromkeys(ELEMENT_SYMBOLS, {}):
            self.g.add_node(f"el:{el}", kind="element", label=el)
        for cl in p.classes:
            self.g.add_node(f"cls:{cl.size_class}", kind="class", label=cl.size_class)
            for el in ELEMENT_SYMBOLS:
                t = cl.tonnes.get(el) or 0.0
                if t:
                    self.g.add_edge(f"el:{el}", f"cls:{cl.size_class}",
                                    kind="loses", element=el, tonnes=round(t, 1))
            for f in cl.forms:
                if f.element != PRIMARY_ELEMENT:  # формы одинаковы — рисуем по ведущему
                    continue
                fid = f"form:{f.form}"
                self.g.add_node(fid, kind="form", label=f.form, recoverable=f.recoverable)
                if f.tonnes:
                    self.g.add_edge(f"cls:{cl.size_class}", fid, kind="as_form",
                                    tonnes=round(f.tonnes, 1), pct=round(f.pct, 1),
                                    recoverable=f.recoverable)

    def stats(self):
        return {"nodes": self.g.number_of_nodes(), "edges": self.g.number_of_edges()}

    def to_layered(self):
        """Сериализация для послойной SVG-визуализации (3 колонки)."""
        layers = {"element": [], "class": [], "form": []}
        for n, d in self.g.nodes(data=True):
            layers[d["kind"]].append({"id": n, "label": d["label"],
                                      "recoverable": d.get("recoverable", None)})
        layers["class"].sort(key=lambda x: class_sort_key(x["label"]))
        layers["element"].sort(key=lambda x: x["label"])
        layers["form"].sort(key=lambda x: (not x["recoverable"], x["label"]))
        edges = [{"src": u, "dst": v, "tonnes": d.get("tonnes", 0),
                  "kind": d["kind"], "recoverable": d.get("recoverable", False)}
                 for u, v, d in self.g.edges(data=True)]
        return {"layers": layers, "edges": edges}
