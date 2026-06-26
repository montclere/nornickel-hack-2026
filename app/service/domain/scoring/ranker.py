"""Интерпретируемый ранкер — чистый домен.

Линейная модель поверх 6 признаков (novelty, risk, value, chain_len, conflict,
cost). Веса — обычный dict (читаемы и редактируемы наружу). rank_score = Σ wᵢ·fᵢ;
вклад каждого признака (wᵢ·fᵢ) сохраняется в гипотезе → «почему такой ранг».

Веса (числа) грузит/сохраняет pipeline через infrastructure/persistence; здесь —
только чистая математика над уже посчитанными признаками.
"""

from __future__ import annotations

from app.service.domain import graph_ops
from app.service.domain.scoring import metrics
from app.service.entities import Hypothesis
from app.service.interfaces import GraphRepository

FEATURES = metrics.FEATURE_NAMES

# стартовые веса-приоры (знак интерпретируем: + повышает ранг, − понижает)
DEFAULT_WEIGHTS: dict[str, float] = {
    "novelty": 1.0,
    "value": 1.2,
    "risk": -1.0,
    "conflict": 0.2,
    "chain_len": -0.2,
    "cost": -0.4,
}


def default_weights() -> dict[str, float]:
    """Копия стартовых весов ранкера."""
    return dict(DEFAULT_WEIGHTS)


def rank(
    hypotheses: list[Hypothesis],
    repo: GraphRepository,
    kpi: str | None = None,
    weights: dict[str, float] | None = None,
    distances: dict[str, float] | None = None,
) -> list[Hypothesis]:
    """Посчитать метрики, проставить rank_score/разложение и отсортировать (desc)."""
    w = dict(weights) if weights else default_weights()
    kpi_id = graph_ops.resolve_kpi_node(repo, kpi) if kpi else None

    scored: list[Hypothesis] = []
    for h in hypotheses:
        distance = distances.get(h.id) if distances else None
        m = metrics.compute(h, repo, kpi_id, distance)
        contributions = {f: w.get(f, 0.0) * m.features[f] for f in FEATURES}
        rank_score = sum(contributions.values())
        scored.append(
            h.model_copy(
                update={
                    "novelty": m.novelty.value,
                    "risk": m.risk.value,
                    "value": m.value.value,
                    "rank_score": rank_score,
                    "novelty_breakdown": m.novelty,
                    "risk_breakdown": m.risk,
                    "value_breakdown": m.value,
                    "rank_contributions": contributions,
                }
            )
        )
    # детерминированный порядок: по убыванию ранга, тай-брейк по id
    scored.sort(key=lambda h: (-(h.rank_score or 0.0), h.id))
    return scored


__all__ = ["FEATURES", "DEFAULT_WEIGHTS", "default_weights", "rank"]
