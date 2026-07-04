# -*- coding: utf-8 -*-
"""Контракт веб-поиска: запрос → список URL. Веб-практики зовут этот интерфейс, а не
конкретный DuckDuckGo — так DDG заменяется на Yandex Search API одним провайдером в DI."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SearchClient(Protocol):
    name: str

    @property
    def available(self) -> bool:
        ...

    def search(self, query: str, n: int) -> list:
        """Вернуть до n URL по запросу (ранжирование/фильтрацию делает вызывающий)."""
        ...
