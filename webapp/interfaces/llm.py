# -*- coding: utf-8 -*-
"""Контракт LLM-клиента. Ветка Б (извлечение) и полировка зовут ТОЛЬКО этот интерфейс —
конкретную реализацию (Yandex сейчас, селф-хост потом) подставляет DI.

factory.llm.Yandex удовлетворяет контракту СТРУКТУРНО (ready/probe/complete), поэтому
адаптер тонкий. Селф-хост: свой класс с тем же контрактом и другим эндпоинтом."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    @property
    def ready(self) -> bool:
        """Есть ли ключ/конфиг (быстрая проверка, без сети)."""
        ...

    def probe(self) -> bool:
        """Реально ли доступен эндпоинт (короткий вызов; для preflight, чтобы не висеть)."""
        ...

    def complete(self, system: str, user: str, timeout: int = 90) -> str:
        ...
