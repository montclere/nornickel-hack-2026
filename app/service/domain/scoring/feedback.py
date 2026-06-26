"""Дообучение ранкера на фидбеке эксперта — чистый домен.

accept/reject → метки 1/0; интерпретируемая логистическая регрессия (sklearn,
с регуляризацией под малые выборки 10-20 примеров) пересчитывает веса признаков.
После дообучения веса меняются (напр. «риск стал весить больше новизны»).

sklearn импортируется ЛЕНИВО внутри `retrain`: лёгкая установка (`pip install -e .`)
без scikit-learn по-прежнему позволяет импортировать домен; обучение требует
`pip install -e '.[domain]'`.
"""

from __future__ import annotations

from app.service.domain import graph_ops
from app.service.domain.scoring import metrics, ranker
from app.service.entities import Feedback, Hypothesis
from app.service.errors import PhoenixError
from app.service.interfaces import GraphRepository

FEATURES = ranker.FEATURES
_LABELS = {"accept": 1, "edit": 1, "reject": 0}  # edit = принято после правки


def retrain(
    samples: list[tuple[dict[str, float], int]],
    current_weights: dict[str, float] | None = None,
    *,
    C: float = 0.5,
    max_iter: int = 1000,
) -> dict[str, float]:
    """Пересчитать веса по выборке (признаки, метка).

    Возвращает текущие/дефолтные веса без изменений, если данных мало или присутствует
    только один класс (нечему учиться). Решатель lbfgs детерминирован.
    """
    weights = dict(current_weights) if current_weights else ranker.default_weights()
    if len(samples) < 2 or len({int(label) for _, label in samples}) < 2:
        return weights

    try:
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise PhoenixError(
            "scoring.retrain требует scikit-learn — установите: pip install -e '.[domain]'"
        ) from exc

    X = [[float(feat.get(f, 0.0)) for f in FEATURES] for feat, _ in samples]
    y = [int(label) for _, label in samples]
    model = LogisticRegression(C=C, max_iter=max_iter)
    model.fit(X, y)
    # интерпретируемый выход: коэффициент на каждый признак (свободный член отбрасываем —
    # на порядок ранжирования он не влияет)
    return {f: float(coef) for f, coef in zip(FEATURES, model.coef_[0])}


def build_samples(
    feedbacks: list[Feedback],
    hypotheses: list[Hypothesis],
    repo: GraphRepository,
    kpi: str | None = None,
) -> list[tuple[dict[str, float], int]]:
    """Собрать выборку (признаки, метка) из фидбека, пересчитав признаки гипотез."""
    kpi_id = graph_ops.resolve_kpi_node(repo, kpi) if kpi else None
    by_id = {h.id: h for h in hypotheses}
    samples: list[tuple[dict[str, float], int]] = []
    for fb in feedbacks:
        hypothesis = by_id.get(fb.hypothesis_id)
        if hypothesis is None or fb.decision not in _LABELS:
            continue
        features = metrics.compute(hypothesis, repo, kpi_id).features
        samples.append((features, _LABELS[fb.decision]))
    return samples


__all__ = ["retrain", "build_samples"]
