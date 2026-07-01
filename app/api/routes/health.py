"""Служебный эндпоинт состояния."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.routes.deps import get_state
from app.api.state import AppState

router = APIRouter(tags=["health"])


@router.get("/health")
def health(state: AppState = Depends(get_state)):
    return {
        "status": "ok",
        "graph_built": state.graph_built,
        "adapter_modes": state.container.adapter_modes,
    }
