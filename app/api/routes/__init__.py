"""FastAPI-роутеры: тонкие контроллеры поверх готовых use-cases.

Разбиты по концернам — каждый файл держит свой APIRouter; здесь они собираются в один.
Граф строится один раз (POST /build_graph) и кэшируется в AppState — /generate за секунды.
Ничего тяжёлого в контроллерах: вся логика — в use-cases (service/pipeline) и домене.

    health.py      GET  /health
    corpus.py      POST /ingest, /build_graph, /research
    hypotheses.py  POST /generate · GET /graph (полный) · GET /graph/path/{id}
    feedback.py    POST /feedback · GET /ranker_weights
    chat.py        POST /chat · GET /agent/trace/{id}
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import chat, corpus, feedback, health, hypotheses

router = APIRouter()
for _module in (health, corpus, hypotheses, feedback, chat):
    router.include_router(_module.router)

__all__ = ["router"]
