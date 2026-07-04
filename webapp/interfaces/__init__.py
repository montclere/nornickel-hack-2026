# -*- coding: utf-8 -*-
"""Контракты (Protocol) внешних клиентов — точка подмены реализаций через DI."""
from webapp.interfaces.llm import LLMClient
from webapp.interfaces.search import SearchClient

__all__ = ["LLMClient", "SearchClient"]
