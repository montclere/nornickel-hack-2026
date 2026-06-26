"""Сборка карточки-гипотезы — домен.

`pattern_fields` готовит структурированные поля для порта `CardPhrasing`;
`assemble` собирает финальную `Hypothesis` из оформленного текста с постпроверкой
«никаких новых сущностей» (`verify_no_new_entities`). Чистый домен: зависит только
от `CardPhrasing` (как от данных), не от Claude напрямую. Без I/O, без LLM,
без импортов из app.infrastructure / app.api.

Интерпретируемость: origin-бейдж + кликабельная цепочка рёбер с цитатами
(evidence_path) уже на гипотезе — карточка сама себя объясняет.
"""

from __future__ import annotations

from app.service.domain.cards.assemble import (
    assemble,
    pattern_fields,
    verify_no_new_entities,
)

__all__ = ["assemble", "pattern_fields", "verify_no_new_entities"]
