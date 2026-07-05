from __future__ import annotations

from fastapi import APIRouter, Depends

from webapp.api.schemas import Health
from webapp.di import get_llm, get_search
from webapp.interfaces import LLMClient, SearchClient

router = APIRouter(tags=["health"])

@router.get("/health", response_model=Health)
def health(llm: LLMClient = Depends(get_llm), search: SearchClient = Depends(get_search)):
    llm_ok = False
    try:
        llm_ok = bool(llm.ready and llm.probe())
    except Exception:
        llm_ok = False
    ocr_ok = False
    try:
        from factory.config import OCR_ENABLED
        if OCR_ENABLED:
            from factory.ext.ocr import YandexOCR
            o = YandexOCR()
            ocr_ok = bool(o.ready and o.probe())
    except Exception:
        ocr_ok = False
    note = ("анализ отчётов, научные статьи и поиск в интернете работают без ключа; "
            "ключ Yandex нужен для чтения литературы и распознавания сканов")
    return Health(ok=True, llm=llm_ok, ocr=ocr_ok, search_backend=search.name,
                  search_available=bool(getattr(search, "available", True)), note=note)
