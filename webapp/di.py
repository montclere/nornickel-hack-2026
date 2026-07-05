from __future__ import annotations

from webapp.adapters.ddg_search import DdgSearch
from webapp.adapters.yandex_llm import YandexLLM
from webapp.adapters.yandex_search import YandexSearch
from webapp.config import settings
from webapp.interfaces import LLMClient, SearchClient


def get_llm() -> LLMClient:
    return YandexLLM()

def get_search() -> SearchClient:
    if settings.SEARCH_BACKEND != "ddg":
        ys = YandexSearch()
        if ys.available:
            return ys
    return DdgSearch()

def get_run_service(llm: LLMClient = None, search: SearchClient = None):

    from webapp.services.run_service import RunService
    return RunService(llm=llm, search=search)

def get_report_service():
    from webapp.services.report_service import ReportService
    return ReportService()
