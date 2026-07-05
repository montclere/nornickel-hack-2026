from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    @property
    def ready(self) -> bool:
        ...

    def probe(self) -> bool:
        ...

    def complete(self, system: str, user: str, timeout: int = 90) -> str:
        ...
