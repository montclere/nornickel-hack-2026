from __future__ import annotations

from factory.enrich.websearch import smart_search, yandex_search_ready


class YandexSearch:

    @property
    def name(self) -> str:

        return "yandex" if yandex_search_ready() else "duckduckgo"

    @property
    def available(self) -> bool:
        return yandex_search_ready()

    def search(self, query: str, n: int) -> list:
        return smart_search(query, n)
