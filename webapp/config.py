# -*- coding: utf-8 -*-
"""Настройки веб-сервиса + ЛИМИТЫ. Локальный инстанс, не публичный."""
from __future__ import annotations

import os
from pathlib import Path


class Settings:
    # где живут прогоны (изоляция по run_id); эфемерно, без БД
    RUNS_DIR = Path(os.environ.get("WEBAPP_RUNS_DIR", "outputs/runs"))

    # Лимитов на размер/число/типы файлов НЕТ: система сама распознаёт, что парсить
    # (ingest пропускает неизвестные форматы). Локальный инстанс — доверяем пользователю.
    MAX_KPI_LEN = 800
    DEFAULT_MAX_CHUNKS = int(os.environ.get("WEBAPP_MAX_CHUNKS", "14"))  # окно ветки Б (правится в форме)

    # какой поисковый бэкенд подсунуть в DI: ddg (без ключа) | yandex (нужен ключ)
    SEARCH_BACKEND = os.environ.get("WEBAPP_SEARCH", "auto")  # auto: yandex если есть ключ, иначе ddg

    # НЕ публичный сервис: без аутентификации, изоляция только по непубличному run_id.
    # Данные фабрик наружу не отправляются (наружу — только термины запроса к
    # подтверждённым источникам: OpenAlex, поисковик, Yandex LLM). См. LIMITATIONS.md.
    LOCAL_ONLY = True


settings = Settings()
