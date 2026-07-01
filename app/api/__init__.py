"""HTTP-граница (FastAPI): тонкие контроллеры поверх use-cases.

`create_app(mode)` собирает контейнер нужного режима, поднимает CORS под фронт и
подключает роутеры. Модульный `app` — точка входа для `uvicorn app.api:app`.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.state import AppState
from app.config import Mode
from app.container import build


def create_app(mode: Mode | None = None, *, db_path: str | None = None) -> FastAPI:
    """Собрать FastAPI-приложение поверх контейнера use-cases."""
    resolved: Mode = mode or os.getenv("PHOENIX_MODE", "fake")  # type: ignore[assignment]
    container = build(resolved, db_path=db_path)

    app = FastAPI(
        title="«Феникс» — фабрика гипотез",
        version="0.1.0",
        description="Ранжированные карточки-гипотезы «ЕСЛИ-ТО-ПОТОМУ ЧТО» над графом знаний.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # под фронт (React+Cytoscape, frontend/)
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.phoenix = AppState(container=container)
    app.include_router(router)
    return app


# точка входа: `uvicorn app.api:app --reload`
app = create_app()

__all__ = ["create_app", "app"]
