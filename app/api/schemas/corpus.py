"""DTO запросов фазы корпуса: приём документов, сборка графа, research.

Соответствуют роутам в [routes/corpus.py]. Тела ответов — доменные сущности
(FastAPI сериализует pydantic v2 напрямую), поэтому здесь только запросы.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.service.entities import Document


class IngestRequest(BaseModel):
    """Приём документов. Если `documents` не заданы — берётся демо-корпус из fixtures."""

    documents: list[Document] | None = None


class BuildGraphRequest(BaseModel):
    """Построение графа. `force=true` пересобирает кэш (иначе идемпотентно)."""

    force: bool = False


class ResearchRequest(BaseModel):
    """Запуск агента-Scout, дозаполняющего граф под целевой KPI."""

    kpi: str = Field(..., examples=["извлечение Ni +2%"])


__all__ = ["IngestRequest", "BuildGraphRequest", "ResearchRequest"]
