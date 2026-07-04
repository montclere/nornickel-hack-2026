# -*- coding: utf-8 -*-
"""Pydantic-контракты запрос/ответ API."""
from __future__ import annotations

from pydantic import BaseModel


class RunCreated(BaseModel):
    run_id: str
    n_fabrics: int
    n_hypotheses: int
    literature: bool
    warnings: list[str] = []
    redirect: str


class Health(BaseModel):
    ok: bool
    llm: bool                 # реально доступен эндпоинт (probe)
    ocr: bool
    search_backend: str
    search_available: bool
    note: str
