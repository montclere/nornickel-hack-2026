"""Оформление текста карточки через LLM (порт CardPhrasing). Реальная реализация —
ClaudeCardPhrasing; оффлайн-версия — FakeCardPhrasing в app.infrastructure.fakes."""

from app.infrastructure.phrasing.claude import ClaudeCardPhrasing

__all__ = ["ClaudeCardPhrasing"]
