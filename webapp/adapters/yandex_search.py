# -*- coding: utf-8 -*-
"""Yandex Search API как ОСНОВНОЙ поиск (официальный REST вместо скрейпинга) с
фолбэком на DuckDuckGo. Реализация живёт в factory.websearch (smart_search) — её же
использует CLI (flex --web); этот адаптер лишь оборачивает под контракт SearchClient."""
from __future__ import annotations

from factory.websearch import smart_search, yandex_search_ready


class YandexSearch:
    """Yandex Search API → при ошибке/пустой выдаче внутри smart_search — DDG."""

    @property
    def name(self) -> str:
        return "yandex (+ddg фолбэк)" if yandex_search_ready() else "duckduckgo"

    @property
    def available(self) -> bool:
        return yandex_search_ready()      # ключ+folder есть → можно ставить основным

    def search(self, query: str, n: int) -> list:
        return smart_search(query, n)
