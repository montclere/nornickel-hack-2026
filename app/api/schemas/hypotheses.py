"""DTO запросов генерации гипотез. Соответствует [routes/hypotheses.py]."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    """KPI → ранжированные карточки-гипотезы поверх снапшота графа."""

    kpi: str = Field(..., examples=["извлечение Ni +2%"])


__all__ = ["GenerateRequest"]
