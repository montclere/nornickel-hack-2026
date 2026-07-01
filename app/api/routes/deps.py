"""Общие зависимости роутеров."""

from __future__ import annotations

from fastapi import Request

from app.api.state import AppState


def get_state(request: Request) -> AppState:
    """Достать AppState (кэш графа + реестр артефактов) из приложения."""
    return request.app.state.phoenix


__all__ = ["get_state"]
