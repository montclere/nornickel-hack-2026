# -*- coding: utf-8 -*-
"""DI: провайдеры зависимостей (интерфейс → реализация). Единственное место, где
выбирается конкретный LLM/поиск. Проброс через FastAPI Depends. Хотите контейнерный DI —
эти же провайдеры тривиально переносятся в Dishka.

Замена реализаций:
  • LLM на селф-хост → верните свой класс с контрактом LLMClient из get_llm();
  • поиск на Yandex Search API → WEBAPP_SEARCH=yandex + доработать adapters/yandex_search.py.
"""
from __future__ import annotations

from webapp.adapters.ddg_search import DdgSearch
from webapp.adapters.yandex_llm import YandexLLM
from webapp.adapters.yandex_search import YandexSearch
from webapp.config import settings
from webapp.interfaces import LLMClient, SearchClient


def get_llm() -> LLMClient:
    return YandexLLM()


def get_search() -> SearchClient:
    """Поиск: Yandex Search API — ОСНОВНОЙ (когда есть ключ), DDG — фолбэк.
    Фолбэк двухуровневый: здесь (нет ключа → DDG) и в рантайме внутри
    smart_search (ошибка/пустая выдача Yandex → DDG на каждом запросе)."""
    if settings.SEARCH_BACKEND != "ddg":     # "auto"/"yandex": предпочесть Yandex
        ys = YandexSearch()
        if ys.available:
            return ys
    return DdgSearch()             # явный ddg или нет ключа


def get_run_service(llm: LLMClient = None, search: SearchClient = None):
    # FastAPI подставит через Depends в роуте; здесь тонкая сборка сервиса
    from webapp.services.run_service import RunService
    return RunService(llm=llm, search=search)


def get_report_service():
    from webapp.services.report_service import ReportService
    return ReportService()
