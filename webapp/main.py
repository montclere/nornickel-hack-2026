# -*- coding: utf-8 -*-
"""Точка входа FastAPI. Локальный инстанс (не публичный).

Запуск:  uv run uvicorn webapp.main:app --host 127.0.0.1 --port 8000
Docker:  см. Dockerfile / docker-compose.yml
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from webapp.config import settings

_STATIC = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Фабрика гипотез — локальный сервис",
                  description="Детерминированное ядро + LLM только для понимания текста. "
                              "Локальный инстанс, данные фабрик наружу не уходят.",
                  version="0.1.0")

    settings.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    _STATIC.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    from webapp.api.routes import expert, export, files, health, pages, runs
    app.include_router(health.router)
    app.include_router(runs.router)
    app.include_router(files.router)
    app.include_router(export.router)
    app.include_router(expert.router)
    app.include_router(pages.router)
    return app


app = create_app()
