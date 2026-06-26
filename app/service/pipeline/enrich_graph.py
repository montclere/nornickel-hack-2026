"""Use-case: research-фаза.

Агент-Scout автономно дозаполняет граф цитированными триплетами, после чего граф
ЗАМОРАЖИВАЕТСЯ в новый снапшот. Генерация гипотез идёт ПОВЕРХ снапшота — это и
даёт воспроизводимость («тот же снапшот → те же гипотезы»).
"""

from __future__ import annotations

from app.service.domain.graph_ops import compute_snapshot_id
from app.service.entities import AgentTrace, GraphSnapshot
from app.service.interfaces import GraphRepository, ResearchAgent


class EnrichGraph:
    def __init__(
        self, research_agent: ResearchAgent, graph_repository: GraphRepository
    ) -> None:
        self.research_agent = research_agent
        self.graph_repository = graph_repository
        # последний трейл Scout — чтобы API мог отдать его в /agent/trace
        self.last_trace: AgentTrace | None = None

    def execute(self, kpi: str) -> GraphSnapshot:
        """Прогнать Scout вокруг KPI, влить новые триплеты в граф, перезаморозить."""
        result = self.research_agent.run("scout", {"kpi": kpi})
        self.last_trace = result.trace

        # TODO: нормализовать новые триплеты → Node/Edge и добавить в граф
        # через self.graph_repository.add_nodes / add_edges (детерминированный сборщик).

        snapshot_id = compute_snapshot_id(result.triplets)
        return GraphSnapshot(
            snapshot_id=snapshot_id, triplet_count=len(result.triplets)
        )
