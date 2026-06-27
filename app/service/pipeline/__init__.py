"""Use-cases-оркестраторы: зовут infrastructure (через порты) и кормят domain.

Каждый use-case — класс: конструктор принимает зависимости (интерфейсы/конкретные
классы), метод `execute(...)` оркеструет один сценарий. Pipeline зависит от
`service` (entities, interfaces, domain), но НЕ от `api`.
"""

from app.service.pipeline.build_graph import BuildGraph
from app.service.pipeline.build_knowledge_base import BuildKnowledgeBase
from app.service.pipeline.chat import Chat
from app.service.pipeline.enrich_graph import EnrichGraph
from app.service.pipeline.generate_hypotheses import GenerateHypotheses
from app.service.pipeline.submit_feedback import SubmitFeedback

__all__ = [
    "BuildKnowledgeBase",
    "BuildGraph",
    "EnrichGraph",
    "GenerateHypotheses",
    "SubmitFeedback",
    "Chat",
]
