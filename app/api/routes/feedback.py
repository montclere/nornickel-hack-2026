"""Обратная связь эксперта и веса ранкера."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.routes.deps import get_state
from app.api.state import AppState
from app.service.domain import scoring
from app.service.entities import Feedback

router = APIRouter(tags=["feedback"])


@router.post("/feedback")
def feedback(fb: Feedback, state: AppState = Depends(get_state)):
    """Решение эксперта → персист + дообучение ранкера → новые веса."""
    container = state.container
    container.feedback_repository.add(fb)
    samples = scoring.build_samples(
        container.feedback_repository.all(),
        list(state.hypotheses.values()),
        container.graph_repository,
        state.kpi,
    )
    state.weights = container.submit_feedback.execute(fb, samples=samples)
    return state.weights


@router.get("/ranker_weights")
def ranker_weights(state: AppState = Depends(get_state)):
    return state.container.ranker_state_store.load_weights()
