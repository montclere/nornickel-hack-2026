"""Оркестратор генерации — чистый домен.

Прогоняет три генератора по KPI-узлу, собирает кандидатов и прогоняет фильтр
анти-грабли. Детерминизм: тот же граф → тот же список в том же порядке.
"""

from __future__ import annotations

from app.service.domain.generation import (
    _shared,
    anti_rake,
    contradictions,
    gaps,
    reanimation,
)
from app.service.entities import Hypothesis
from app.service.interfaces import GraphRepository


def generate(repo: GraphRepository, kpi: str) -> list[Hypothesis]:
    """KPI → кандидаты от трёх генераторов → анти-грабли → детерминированный порядок."""
    kpi_id = _shared.resolve_kpi_node(repo, kpi)

    candidates: list[Hypothesis] = []
    candidates += gaps.generate(repo, kpi_id)
    candidates += reanimation.generate(repo, kpi_id)
    candidates += contradictions.generate(repo, kpi_id)

    candidates = anti_rake.apply(repo, candidates)
    candidates.sort(key=lambda h: (_shared.ORIGIN_ORDER.get(h.origin, 99), h.id))
    return candidates


__all__ = ["generate"]
