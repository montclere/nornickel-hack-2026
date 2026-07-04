# -*- coding: utf-8 -*-
"""Заглушка Yandex Search API под контракт SearchClient — точка замены DDG на надёжный
поиск. Реализовать `search()` (endpoint https://searchapi.api.cloud.yandex.net/... через
factory.client.get_json/post_json) и подставить в DI (WEBAPP_SEARCH=yandex). Пока не
готово → available=False, DI откатывается на DDG."""
from __future__ import annotations

import os


class YandexSearch:
    name = "yandex-search"

    def __init__(self, api_key: str | None = None, folder: str | None = None):
        self.api_key = api_key or os.environ.get("YANDEX_SEARCH_KEY")
        self.folder = folder or os.environ.get("YANDEX_FOLDER_ID")

    @property
    def available(self) -> bool:
        # включим, когда реализуем search(); пока False → DI берёт DDG
        return False

    def search(self, query: str, n: int) -> list:
        raise NotImplementedError(
            "Yandex Search API ещё не подключён — подставьте ключ и реализуйте запрос "
            "к searchapi.api.cloud.yandex.net (через factory.client), затем available=True")
