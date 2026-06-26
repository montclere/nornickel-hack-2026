"""Генерация гипотез — детерминированное ядро.

Три генератора + фильтр «анти-грабли», все работают ПОВЕРХ замороженного графа
через порт `GraphRepository`:

- gaps.py          РАЗРЫВЫ (ABC Свонсона): A→B и B→C при отсутствии прямого A→C.
- reanimation.py   РЕАНИМАЦИЯ: провал с устаревшей причиной + свежий факт, её снимающий.
- contradictions.py ПРОТИВОРЕЧИЯ: конфликтующие рёбра разных лет → скрытое условие.
- anti_rake.py     ФИЛЬТР: сверка кандидата с кладбищем провалов (graveyard_check).
- orchestrator.py  прогон всех трёх по KPI-узлу + анти-грабли.

Детерминизм: тот же граф → тот же список в том же порядке. Без I/O, без LLM,
без импортов из app.infrastructure / app.api.
"""

from __future__ import annotations

from app.service.domain.generation import (
    anti_rake,
    contradictions,
    gaps,
    orchestrator,
    reanimation,
)
from app.service.entities import Hypothesis
from app.service.interfaces import GraphRepository


def generate_candidates(repo: GraphRepository, kpi: str) -> list[Hypothesis]:
    """Прогнать три генератора по KPI-узлу и отфильтровать анти-граблями."""
    return orchestrator.generate(repo, kpi)


__all__ = [
    "generate_candidates",
    "gaps",
    "reanimation",
    "contradictions",
    "anti_rake",
    "orchestrator",
]
