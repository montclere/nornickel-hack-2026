"""Метрики novelty / risk / value — чистый домен.

Каждая метрика → число в [0,1] + разложение (`components`) для UI. Граф — только
через порт `GraphRepository`. Векторные расстояния для novelty считает
`infrastructure/embeddings`; в домен они приходят готовыми (`embedding_distance`),
сам домен модель не зовёт. Формулы детерминированы: тот же граф → те же числа.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from app.service.entities import Hypothesis, MetricBreakdown
from app.service.interfaces import GraphRepository

# --- калибровочные константы (стартовые, прозрачные) -------------------------
DEG_CAP = 6  # «насыщение» степени узла: выше → узел хорошо изучен → менее новый
CHAIN_CAP = 4  # нормировка длины цепочки доказательств
COST_CAP = 3_000_000  # опорная стоимость проверки (руб.) для нормировки
CONFLICT_CAP = 3  # насыщение конфликтности
SUPPORT_CAP = 2  # насыщение числа подтверждающих рёбер к KPI
TRL_BY_TYPE: dict[str, int] = {
    "KPI": 9, "process": 8, "parameter": 7, "material": 6, "reagent": 5, "failure": 2,
}

# порядок признаков ранкера (5-6 признаков, см. ranker.py)
FEATURE_NAMES = ["novelty", "risk", "value", "chain_len", "conflict", "cost"]


@dataclass
class Metrics:
    """Метрики гипотезы + готовый вектор признаков для ранкера."""

    novelty: MetricBreakdown
    risk: MetricBreakdown
    value: MetricBreakdown
    features: dict[str, float]


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _involved(hypothesis: Hypothesis) -> set[str]:
    ids: set[str] = set()
    for edge in hypothesis.evidence_path:
        ids.add(edge.source)
        ids.add(edge.target)
    return ids


def _degree(repo: GraphRepository, node_id: str) -> int:
    return len(repo.out_edges(node_id)) + len(repo.in_edges(node_id))


def _conflict_norm(repo: GraphRepository, involved: set[str]) -> float:
    touching = 0
    for a, b in repo.conflicting_edges():
        if {a.source, a.target, b.source, b.target} & involved:
            touching += 1
    return min(touching, CONFLICT_CAP) / CONFLICT_CAP


def _chain_norm(hypothesis: Hypothesis) -> float:
    return min(len(hypothesis.evidence_path), CHAIN_CAP) / CHAIN_CAP


def _cost_norm(hypothesis: Hypothesis) -> float:
    return min(hypothesis.experiment_protocol.cost_rub, COST_CAP) / COST_CAP


def novelty(
    hypothesis: Hypothesis, repo: GraphRepository, embedding_distance: float | None = None
) -> MetricBreakdown:
    """Редкость пути в графе (+ векторная удалённость, если передана)."""
    involved = _involved(hypothesis)
    avg_deg = mean(_degree(repo, n) for n in involved) if involved else 0.0
    path_rarity = _clamp01(1 - min(avg_deg, DEG_CAP) / DEG_CAP)
    components = {"path_rarity": path_rarity}
    if embedding_distance is not None:
        dist = _clamp01(embedding_distance)
        components["embedding_distance"] = dist
        result = 0.5 * path_rarity + 0.5 * dist
    else:
        result = path_rarity
    return MetricBreakdown(value=_clamp01(result), components=components)


def risk(hypothesis: Hypothesis, repo: GraphRepository) -> MetricBreakdown:
    """TRL компонентов + конфликтность источников + пометка кладбища."""
    involved = _involved(hypothesis)
    trls = [
        TRL_BY_TYPE.get(node.type, 5)
        for node in (repo.get_node(i) for i in involved)
        if node is not None
    ]
    trl_risk = _clamp01(1 - (mean(trls) if trls else 5) / 9)
    conflict_risk = _conflict_norm(repo, involved)
    graveyard_risk = 0.3 if hypothesis.graveyard_check.warning else 0.0
    result = _clamp01(0.5 * trl_risk + 0.3 * conflict_risk + 0.2 * graveyard_risk)
    return MetricBreakdown(
        value=result,
        components={
            "trl_risk": trl_risk,
            "source_conflict": conflict_risk,
            "graveyard": graveyard_risk,
        },
    )


def value(
    hypothesis: Hypothesis, repo: GraphRepository, kpi_id: str | None = None
) -> MetricBreakdown:
    """Чувствительность KPI к рычагу (исторические рёбра) с поправкой на стоимость."""
    involved = _involved(hypothesis)
    if kpi_id:
        support = sum(
            1 for e in repo.in_edges(kpi_id) if e.source in involved and e.sign != "0"
        )
        sensitivity = min(support, SUPPORT_CAP) / SUPPORT_CAP
    else:
        sensitivity = 0.5  # KPI не задан → нейтрально
    cost_adjustment = 1 - _cost_norm(hypothesis)
    result = _clamp01(0.6 * sensitivity + 0.4 * cost_adjustment)
    return MetricBreakdown(
        value=result,
        components={"kpi_sensitivity": sensitivity, "cost_adjustment": cost_adjustment},
    )


def compute(
    hypothesis: Hypothesis,
    repo: GraphRepository,
    kpi_id: str | None = None,
    embedding_distance: float | None = None,
) -> Metrics:
    """Все метрики гипотезы + вектор из 6 признаков для ранкера."""
    involved = _involved(hypothesis)
    nov = novelty(hypothesis, repo, embedding_distance)
    rsk = risk(hypothesis, repo)
    val = value(hypothesis, repo, kpi_id)
    features = {
        "novelty": nov.value,
        "risk": rsk.value,
        "value": val.value,
        "chain_len": _chain_norm(hypothesis),
        "conflict": _conflict_norm(repo, involved),
        "cost": _cost_norm(hypothesis),
    }
    return Metrics(novelty=nov, risk=rsk, value=val, features=features)


__all__ = ["Metrics", "FEATURE_NAMES", "novelty", "risk", "value", "compute"]
