"""DTO запросов чата по графу. Соответствует [routes/chat.py]."""

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Вопрос к графу (read-only). `kpi` опционален — уточняет контекст ответа."""

    question: str
    kpi: str | None = None


__all__ = ["ChatRequest"]
