from __future__ import annotations

from factory.enrich.websearch import _search_ddg


class DdgSearch:
    name = "duckduckgo"

    @property
    def available(self) -> bool:
        return True

    def search(self, query: str, n: int) -> list:
        return _search_ddg(query, n)
