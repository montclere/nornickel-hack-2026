"""Автономный агент-исследователь на LangGraph (реализация порта ResearchAgent).

Один рантайм, два режима: mission="scout" (дозаполняет граф цитированными фактами,
plan→act→observe→reflect→loop|stop с бюджетом) и mission="chat" (read-only ответ по
графу со ссылками). Единственный персистентный эффект scout — валидированные Triplet
(через цитатный гейт). Агент НЕ выбирает гипотезы и НЕ строит граф — только добывает факты.
"""

from app.infrastructure.agent.scout import LangGraphResearchAgent

__all__ = ["LangGraphResearchAgent"]
