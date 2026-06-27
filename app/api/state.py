"""Состояние API-сессии.

Граф строится один раз и кэшируется (демо без таймаутов: /generate за секунды).
Транзиентные артефакты (ранжированные карточки, трейлы агента) держим в памяти и
адресуем по id; долговременное (корпус/фидбек/веса) — в SQLite контейнера.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.config import DATA_DIR, FIXTURES_DIR
from app.container import Container
from app.service.domain import scoring
from app.service.entities import (
    AgentTrace,
    Edge,
    GraphSnapshot,
    Hypothesis,
    Node,
    Triplet,
)


@dataclass
class AppState:
    """Кэш графа и реестр транзиентных артефактов поверх контейнера."""

    container: Container
    graph_built: bool = False
    snapshot: GraphSnapshot | None = None
    kpi: str | None = None
    triplets: list[Triplet] = field(default_factory=list)
    hypotheses: dict[str, Hypothesis] = field(default_factory=dict)
    traces: dict[str, AgentTrace] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=scoring.default_weights)

    # --- граф (строится один раз, кэшируется) ---
    def build_graph(self, *, force: bool = False) -> GraphSnapshot:
        """Идемпотентно собрать граф и заморозить снапшот (кэшируется).

        В real/mix-режиме, если есть собранный `data/graph.json`
        (scripts/build_graph.py), грузим реальный граф знаний; иначе — демо-фикстуры.
        """
        if self.graph_built and not force and self.snapshot is not None:
            return self.snapshot
        from app.service.domain.graph_ops import graph_snapshot_id

        repo = self.container.graph_repository
        graph_file = DATA_DIR / "graph.json"
        if self.container.settings.mode != "fake" and graph_file.exists():
            repo.load(graph_file)  # реальный граф (scripts/build_graph.py)
        else:
            repo.add_nodes([Node(**n) for n in _load("nodes.json")])
            repo.add_edges([Edge(**e) for e in _load("edges.json")])
        # снапшот по рёбрам графа: research дозаполнит граф → id изменится
        self.snapshot = GraphSnapshot(
            snapshot_id=graph_snapshot_id(repo), triplet_count=len(repo.all_edges())
        )
        self.graph_built = True
        return self.snapshot

    # --- реестры ---
    def store_hypotheses(self, hypotheses: list[Hypothesis]) -> None:
        for h in hypotheses:
            self.hypotheses[h.id] = h

    def store_trace(self, trace: AgentTrace) -> None:
        self.traces[trace.id] = trace


def _load(name: str):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


__all__ = ["AppState"]
