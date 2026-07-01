"""Use-case: research-фаза.

Агент-Scout автономно дозаполняет граф цитированными триплетами; новые факты
проходят через тот же детерминированный сборщик (нормализация → Node/Edge), что и
основная сборка, после чего граф ПЕРЕЗАМОРАЖИВАЕТСЯ в новый снапшот. Генерация
гипотез идёт ПОВЕРХ снапшота — «тот же снапшот → те же гипотезы».
"""

from __future__ import annotations

from app.service.domain.graph_ops import graph_snapshot_id
from app.service.entities import AgentTrace, GraphSnapshot
from app.service.interfaces import GraphRepository, ResearchAgent
from app.service.pipeline.build_graph import build_nodes_and_edges


class EnrichGraph:
    def __init__(
        self, research_agent: ResearchAgent, graph_repository: GraphRepository, normalizer
    ) -> None:
        self.research_agent = research_agent
        self.graph_repository = graph_repository
        self.normalizer = normalizer
        # последний трейл Scout — чтобы API мог отдать его в /agent/trace
        self.last_trace: AgentTrace | None = None

    def execute(self, kpi: str) -> GraphSnapshot:
        """Прогнать Scout вокруг KPI, влить новые триплеты в граф, перезаморозить снапшот."""
        result = self.research_agent.run("scout", {"kpi": kpi})
        self.last_trace = result.trace

        if result.triplets:
            nodes, edges = build_nodes_and_edges(result.triplets, self.normalizer)
            self.graph_repository.add_nodes(nodes)
            self.graph_repository.add_edges(edges)

        # снапшот по текущему состоянию графа: добавил факты → новый id
        return GraphSnapshot(
            snapshot_id=graph_snapshot_id(self.graph_repository),
            triplet_count=len(self.graph_repository.all_edges()),
        )
