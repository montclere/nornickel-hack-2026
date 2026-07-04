# -*- coding: utf-8 -*-
"""Адаптер Yandex AI Studio под контракт LLMClient.

Для селф-хоста своей модели — сделать такой же класс с методами ready/probe/complete и
другим base_url (см. factory.config.YANDEX_BASE_URL / env YANDEX_BASE_URL); DI подставит
его вместо этого. Данные фабрик сюда не уходят — только тексты фрагментов знаний."""
from __future__ import annotations

from factory.llm import Yandex


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
        """Объект, который принимают factory-функции (extract_relations, Phraser): у него
        те же .ready/.complete. Возвращаем внутренний Yandex."""
        return self._impl
