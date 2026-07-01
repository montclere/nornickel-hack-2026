"""Скоринг и интерпретируемый ранкер — домен.

- metrics.py   novelty / risk / value по свойствам графа (число + разложение для UI).
- ranker.py    интерпретируемая линейная модель с видимыми весами (dict); сортирует.
- feedback.py  дообучение на Feedback (accept/reject) — веса сдвигаются.

Воспроизводимо: тот же граф → те же числа. Без I/O, без LLM, без импортов из
app.infrastructure / app.api. sklearn используется как чистая математика внутри
домена (ленивый импорт в feedback.retrain).
"""

from __future__ import annotations

from app.service.domain.scoring import feedback, metrics, ranker
from app.service.domain.scoring.feedback import build_samples, retrain
from app.service.domain.scoring.metrics import Metrics
from app.service.domain.scoring.metrics import compute as compute_metrics
from app.service.domain.scoring.ranker import (
    DEFAULT_WEIGHTS,
    FEATURES,
    default_weights,
    rank,
)

__all__ = [
    "metrics",
    "ranker",
    "feedback",
    "compute_metrics",
    "Metrics",
    "rank",
    "default_weights",
    "retrain",
    "build_samples",
    "DEFAULT_WEIGHTS",
    "FEATURES",
]
