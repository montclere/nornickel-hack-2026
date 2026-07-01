"""Use-case: обратная связь эксперта → пересчёт весов ранкера.

accept/reject/edit с причиной дообучают интерпретируемую модель; новые веса
сохраняются (через infrastructure/persistence — `RankerStateStore`).
"""

from __future__ import annotations

from typing import Protocol

from app.service.domain import scoring
from app.service.entities import Feedback


class RankerStateStore(Protocol):
    """Персист весов ранкера (конкретная реализация — SQLite)."""

    def load_weights(self) -> dict[str, float]: ...

    def save_weights(self, weights: dict[str, float]) -> None: ...


class SubmitFeedback:
    def __init__(self, ranker_state_store: RankerStateStore | None = None) -> None:
        self.ranker_state_store = ranker_state_store

    def execute(
        self,
        feedback: Feedback,
        samples: list[tuple[dict[str, float], int]] | None = None,
    ) -> dict[str, float]:
        """Дообучить веса на накопленном фидбеке, вернуть новые веса.

        Дообучение — батчевое (10-20 примеров): `samples` собираются из истории
        карточек+решений через `scoring.build_samples`. Без выборки веса не меняются.

        TODO: сохранять `feedback` и карточки в persistence, собирать
        `samples` оттуда, чтобы веса реально сдвигались по мере накопления оценок.
        """
        current = (
            self.ranker_state_store.load_weights()
            if self.ranker_state_store
            else scoring.default_weights()
        )

        new_weights = scoring.retrain(samples or [], current)

        if self.ranker_state_store:
            self.ranker_state_store.save_weights(new_weights)
        return new_weights
