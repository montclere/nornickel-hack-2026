"""Приём корпуса, сборка графа, research-фаза.

ingest → build_graph → research. Граф строится один раз и кэшируется в AppState.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from app.api.routes.deps import get_state
from app.api.schemas import BuildGraphRequest, IngestRequest, ResearchRequest
from app.api.state import AppState
from app.config import FIXTURES_DIR
from app.service.entities import Document

router = APIRouter(tags=["corpus"])


@router.post("/ingest")
def ingest(req: IngestRequest, state: AppState = Depends(get_state)):
    """Приём базы знаний (OCR сканов + извлечение фактов) → триплеты."""
    if req.documents is not None:
        documents = req.documents
    else:
        documents = [Document(**d) for d in _fixture("documents.json")]
    triplets = state.container.build_knowledge_base.execute(documents)
    state.container.corpus_repository.save_documents(documents)
    state.container.corpus_repository.save_triplets(triplets)
    state.triplets = triplets
    return {"documents": len(documents), "triplets": len(triplets)}


@router.post("/build_graph")
def build_graph(req: BuildGraphRequest, state: AppState = Depends(get_state)):
    """Извлечение → нормализация → граф + снапшот. Идемпотентно (кэш)."""
    snapshot = state.build_graph(force=req.force)
    repo = state.container.graph_repository
    return {
        "snapshot_id": snapshot.snapshot_id,
        "triplet_count": snapshot.triplet_count,
        "nodes": len(repo.all_nodes()),
        "edges": len(repo.all_edges()),
    }


@router.post("/research")
def research(req: ResearchRequest, state: AppState = Depends(get_state)):
    """Агент-Scout дозаполняет граф и перезамораживает снапшот."""
    state.build_graph()
    snapshot = state.container.enrich_graph.execute(req.kpi)
    trace = state.container.enrich_graph.last_trace
    if trace is not None:
        state.store_trace(trace)
    return {
        "snapshot_id": snapshot.snapshot_id,
        "triplet_count": snapshot.triplet_count,
        "trace_id": trace.id if trace else None,
    }


def _fixture(name: str):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
