"""Use-case: генерация ранжированных карточек-гипотез.

Выбор кандидатов делает детерминированное ядро `domain.generation` поверх графа;
скоринг — `domain.scoring`; оформление текста карточки — порт `CardPhrasing`
(LLM только переформулирует, новых фактов не вводит).
"""

from __future__ import annotations

from app.service.domain import cards, generation, scoring
from app.service.entities import Hypothesis
from app.service.interfaces import CardPhrasing, GraphRepository


class GenerateHypotheses:
    def __init__(
        self, graph_repository: GraphRepository, card_phrasing: CardPhrasing
    ) -> None:
        self.graph_repository = graph_repository
        self.card_phrasing = card_phrasing

    def execute(self, kpi: str) -> list[Hypothesis]:
        """KPI → кандидаты (домен) → скоринг (домен) → оформление текста (порт)."""
        candidates = generation.generate_candidates(self.graph_repository, kpi)
        ranked = scoring.rank(candidates, self.graph_repository, kpi)
        return [self._phrase(hypothesis, kpi) for hypothesis in ranked]

    def _phrase(self, hypothesis: Hypothesis, kpi: str) -> Hypothesis:
        """Оформить текст через порт CardPhrasing; домен проверяет «нет новых сущностей»."""
        fields = cards.pattern_fields(hypothesis, self.graph_repository, kpi)
        phrased = self.card_phrasing.phrase(fields)
        return cards.assemble(hypothesis, phrased, self.graph_repository, kpi)
