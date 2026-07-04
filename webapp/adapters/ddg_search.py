# -*- coding: utf-8 -*-
"""Поиск через DuckDuckGo (без ключа) — делегирует в factory.websearch._search_ddg,
который уже ранжирует русские/индустриальные домены выше. Best-effort: DDG может
бот-блокировать по IP (тогда вернёт [], веб-практики останутся пустыми — не падаем)."""
from __future__ import annotations

from factory.websearch import _search_ddg


class DdgSearch:
    name = "duckduckgo"

    @property
    def available(self) -> bool:
        return True                     # ключ не нужен; фактическую доступность решает сеть

    def search(self, query: str, n: int) -> list:
        return _search_ddg(query, n)
