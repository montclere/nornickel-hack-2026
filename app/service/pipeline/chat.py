"""Use-case: чат по графу, read-only Q&A.

Тот же агентный рантайм в режиме mission="chat": сначала ищет ответ в графе, при
нехватке — догоняет веб. ОТВЕЧАЕТ со ссылками, но граф НЕ меняет и снапшот
генерации НЕ трогает (детерминизм генерации не нарушается).
"""

from __future__ import annotations

from app.service.entities import AgentResult
from app.service.interfaces import GraphRepository, ResearchAgent


class Chat:
    def __init__(
        self, research_agent: ResearchAgent, graph_repository: GraphRepository
    ) -> None:
        self.research_agent = research_agent
        self.graph_repository = graph_repository

    def execute(self, question: str, kpi: str | None = None) -> AgentResult:
        """Ответить на вопрос по графу со ссылками. READ-ONLY: граф не изменяется."""
        return self.research_agent.run(
            "chat", {"question": question, "kpi": kpi}
        )
