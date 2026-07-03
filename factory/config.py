# -*- coding: utf-8 -*-
"""Центральная конфигурация. Всё настраиваемое — в одном месте, env переопределяет.

Порядок: сначала подхватываем .env (поиск вверх от пакета), потом читаем os.environ.
"""
from __future__ import annotations

import os


def load_env():
    """Подхватить .env (поиск вверх от пакета); уже выставленные переменные не трогаем."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        p = os.path.join(d, ".env")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return True
        d = os.path.dirname(d)
    return False


load_env()

# --- продукт ---
DEFAULT_KPI = os.environ.get(
    "FACTORY_KPI", "снизить потери извлекаемого металла с хвостами")
OUTPUTS_DIR = os.environ.get("FACTORY_OUTPUTS", "outputs")
DEFAULT_CACHE = os.path.join(OUTPUTS_DIR, "kb_cache.json")

# --- LLM (Yandex AI Studio) ---
YANDEX_BASE_URL = os.environ.get(
    "YANDEX_BASE_URL", "https://llm.api.cloud.yandex.net/foundationModels/v1")
YANDEX_MODEL = os.environ.get("YANDEX_MODEL", "yandexgpt/latest")

# --- извлечение из текста ---
MAX_CHUNK_CHARS = int(os.environ.get("FACTORY_MAX_CHUNK_CHARS", "3500"))  # окно LLM
MIN_PROSE_CHARS = int(os.environ.get("FACTORY_MIN_PROSE_CHARS", "200"))  # отсев огрызков
LLM_WORKERS = int(os.environ.get("FACTORY_LLM_WORKERS", "4"))            # параллельные вызовы
LLM_MAX_RETRIES = int(os.environ.get("FACTORY_LLM_RETRIES", "4"))        # backoff на 429/5xx

# --- LLM-as-judge (качественная метрика ветки Б) ---
# по умолчанию — та же модель Yandex; в идеале судья ≠ генератору (см. judge.py),
# поэтому модель судьи вынесена отдельно и переопределяется через env.
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", YANDEX_MODEL)
JUDGE_CACHE = os.path.join(OUTPUTS_DIR, "judge_cache.json")

# --- OCR (Yandex Vision) — картинки и сканы PDF → текст ---
OCR_ENABLED = os.environ.get("FACTORY_OCR", "1") not in ("0", "false", "no", "off")
OCR_BASE_URL = os.environ.get("YANDEX_OCR_URL", "https://ocr.api.cloud.yandex.net")
OCR_MODEL = os.environ.get("OCR_MODEL", "page")           # page | table | handwritten
OCR_LANGS = [s for s in os.environ.get("OCR_LANGS", "ru,en").split(",") if s]
OCR_DPI = int(os.environ.get("OCR_DPI", "200"))           # растеризация страниц PDF под OCR
OCR_MIN_CHARS = int(os.environ.get("OCR_MIN_CHARS", "8"))  # короче — считаем «пусто»
OCR_PDF_MAX_PAGES = int(os.environ.get("OCR_PDF_MAX_PAGES", "20"))  # предохранитель от скан-книг
OCR_CACHE = os.path.join(OUTPUTS_DIR, "ocr_cache.json")
