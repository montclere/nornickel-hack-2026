from __future__ import annotations

from factory.ext.llm import Yandex


class YandexLLM:
    def __init__(self, temperature: float = 0.0):
        self._impl = Yandex(temperature=temperature)

    @property
    def ready(self) -> bool:
        return self._impl.ready

    def probe(self) -> bool:
        return self._impl.probe()

    def complete(self, system: str, user: str, timeout: int = 90) -> str:
        return self._impl.complete(system, user, timeout)

    @property
    def raw(self):
        return self._impl
