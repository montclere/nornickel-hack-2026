from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SearchClient(Protocol):
    name: str

    @property
    def available(self) -> bool:
        ...

    def search(self, query: str, n: int) -> list:
        ...
