"""Pydantic DTO запросов API, разбитые по концернам (как routes/).

Тела ответов — чаще всего сами доменные сущности (`app.service.entities`):
FastAPI сериализует pydantic v2 напрямую, поэтому отдельных response-DTO нет.

    corpus.py      IngestRequest · BuildGraphRequest · ResearchRequest
    hypotheses.py  GenerateRequest
    chat.py        ChatRequest
"""

from __future__ import annotations

from app.api.schemas.chat import ChatRequest
from app.api.schemas.corpus import BuildGraphRequest, IngestRequest, ResearchRequest
from app.api.schemas.hypotheses import GenerateRequest

__all__ = [
    "IngestRequest",
    "BuildGraphRequest",
    "ResearchRequest",
    "GenerateRequest",
    "ChatRequest",
]
