"""Извлечение фактов из фрагментов через LLM (реализация порта FactExtractor).

GroqFactExtractor зовёт OpenAI-совместимый API (по умолчанию Groq) и пропускает
каждый триплет через цитатный гейт: цитата-доказательство обязана присутствовать
в исходном фрагменте дословно, иначе триплет отбраковывается.
"""

from app.infrastructure.extraction.groq import GroqFactExtractor, quote_is_verbatim

__all__ = ["GroqFactExtractor", "quote_is_verbatim"]
