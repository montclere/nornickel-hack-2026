"""Чат по графу (read-only) и трейл агента."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.routes.deps import get_state
from app.api.schemas import ChatRequest
from app.api.state import AppState

router = APIRouter(tags=["chat"])


@router.post("/chat")
def chat(req: ChatRequest, state: AppState = Depends(get_state)):
    """Read-only Q&A по графу со ссылками. Граф НЕ меняется."""
    result = state.container.chat.execute(req.question, req.kpi)
    state.store_trace(result.trace)
    return {
        "answer": result.answer,
        "sources": result.sources,
        "trace_id": result.trace.id,
    }


@router.get("/agent/trace/{trace_id}")
def agent_trace(trace_id: str, state: AppState = Depends(get_state)):
    """Трейл агента: мысль → запрос → источник → цитата."""
    trace = state.traces.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Неизвестный trace_id")
    return trace
