"""Генерация карточек и их цепочка доказательств для UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.api.routes.deps import get_state
from app.api.schemas import GenerateRequest
from app.api.state import AppState
from app.service.entities import Hypothesis

router = APIRouter(tags=["hypotheses"])


@router.post("/generate", response_model=list[Hypothesis])
def generate(req: GenerateRequest, state: AppState = Depends(get_state)):
    """KPI → ранжированные карточки (поверх снапшота). Должно быть < 2 сек."""
    state.build_graph()
    state.kpi = req.kpi
    hypotheses = state.container.generate_hypotheses.execute(req.kpi)
    state.store_hypotheses(hypotheses)
    return hypotheses


@router.get("/graph/pyvis", response_class=HTMLResponse)
def graph_pyvis(state: AppState = Depends(get_state)):
    """Полный граф знаний как интерактивная HTML-страница (Pyvis/vis.js).

    Фронт встраивает её в <iframe>. Физика, перетаскивание, подсветка окрестности
    при наведении; цитаты и первоисточники — во всплывающих подсказках рёбер.
    """
    state.build_graph()
    repo = state.container.graph_repository
    try:
        from app.api.pyvis_view import build_graph_html
    except ImportError as exc:  # pyvis не установлен
        raise HTTPException(
            status_code=503,
            detail="Pyvis не установлен: pip install -e '.[infra]'",
        ) from exc
    return HTMLResponse(content=build_graph_html(repo.all_nodes(), repo.all_edges()))


@router.get("/graph")
def graph_full(state: AppState = Depends(get_state)):
    """Полный граф знаний в формате Cytoscape — общий обзор (Connected-Papers-вид).

    `degree` на узле = число инцидентных рёбер (размер узла в визуализации).
    Граф строится один раз и кэшируется, поэтому эндпойнт работает и до /generate.
    """
    state.build_graph()
    repo = state.container.graph_repository
    all_edges = repo.all_edges()
    degree: dict[str, int] = {}
    for e in all_edges:
        degree[e.source] = degree.get(e.source, 0) + 1
        degree[e.target] = degree.get(e.target, 0) + 1
    nodes = [
        {
            "data": {
                "id": n.id,
                "label": n.label,
                "type": n.type,
                "degree": degree.get(n.id, 0),
                "closure_reason": n.closure_reason,
            }
        }
        for n in repo.all_nodes()
    ]
    edges = [
        {
            "data": {
                "id": f"e{i}",
                "source": e.source,
                "target": e.target,
                "sign": e.sign,
                "year": e.year,
                "quote": e.evidence_quote,
                "doc_id": e.doc_id,
            }
        }
        for i, e in enumerate(all_edges)
    ]
    return {
        "snapshot_id": state.snapshot.snapshot_id if state.snapshot else None,
        "elements": {"nodes": nodes, "edges": edges},
    }


@router.get("/graph/path/{hypothesis_id}")
def graph_path(hypothesis_id: str, state: AppState = Depends(get_state)):
    """Узлы/рёбра цепочки доказательств гипотезы — в формате Cytoscape."""
    hypothesis = state.hypotheses.get(hypothesis_id)
    if hypothesis is None:
        raise HTTPException(status_code=404, detail="Неизвестная гипотеза")
    repo = state.container.graph_repository
    seen: set[str] = set()
    nodes = []
    for edge in hypothesis.evidence_path:
        for node_id in (edge.source, edge.target):
            if node_id in seen:
                continue
            seen.add(node_id)
            node = repo.get_node(node_id)
            nodes.append(
                {
                    "data": {
                        "id": node_id,
                        "label": node.label if node else node_id,
                        "type": node.type if node else "unknown",
                    }
                }
            )
    edges = [
        {
            "data": {
                "id": f"e{i}",
                "source": edge.source,
                "target": edge.target,
                "sign": edge.sign,
                "year": edge.year,
                "quote": edge.evidence_quote,
                "doc_id": edge.doc_id,
            }
        }
        for i, edge in enumerate(hypothesis.evidence_path)
    ]
    return {"hypothesis_id": hypothesis_id, "elements": {"nodes": nodes, "edges": edges}}
