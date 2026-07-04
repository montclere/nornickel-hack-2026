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
# Намеренно НЕТ DEFAULT_KPI. Молчаливый дефолт на реальный бизнес-вопрос («что
# оптимизируем») ввёл бы пользователя в заблуждение — лучше явная ошибка, чем тихая
# подмена цели. KPI обязателен во всех CLI-командах (--kpi required) и в HypothesisFactory.
OUTPUTS_DIR = os.environ.get("FACTORY_OUTPUTS", "outputs")
DEFAULT_CACHE = os.path.join(OUTPUTS_DIR, "kb_cache.json")
# конфиг ПОСЛЕДНЕГО запуска (KPI и параметры) — создаёт flex.py, читают benchmark/judge,
# если им не передали свой --kpi. Не тайный дефолт: это переиспользование РЕАЛЬНОГО
# значения из настоящего явного запуска, с объявлением источника в выводе (см. runconfig.py)
RUN_CONFIG_PATH = os.path.join(OUTPUTS_DIR, "last_run.json")

# --- вторичная гипотеза класса (см. generator._secondary): доля извлекаемого
# тоннажа класса в НЕдоминирующей форме, с которой генерируется второе направление
# (напр. класс с доминирующим закрытым минералом, но заметной раскрытой долей →
# помимо «доизмельчения» честно предложить и флотационное направление) ---
# дефолт 0.30 подобран свипом по golden-бенчмарку: recall 27/27 = 100% (было 85%),
# precision Примеров 1/4 остаётся 100% (0.20–0.25 дают тот же recall, но шире
# задевают precision; 0.40 теряет recall Примера 3)
SECONDARY_MIN_SHARE = float(os.environ.get("FACTORY_SECONDARY_SHARE", "0.30"))

# --- фидбэк эксперта (см. feedback.py): человекочитаемая база вердиктов,
# применяется детерминированным ре-ранком; FACTORY_FEEDBACK=0 — отключить ---
FEEDBACK_PATH = os.environ.get("FACTORY_FEEDBACK_PATH",
                               os.path.join(OUTPUTS_DIR, "feedback.json"))
FEEDBACK_ENABLED = os.environ.get("FACTORY_FEEDBACK", "1") not in ("0", "false", "no", "off")

# --- LLM (Yandex AI Studio) ---
YANDEX_BASE_URL = os.environ.get(
    "YANDEX_BASE_URL", "https://llm.api.cloud.yandex.net/foundationModels/v1")
YANDEX_MODEL = os.environ.get("YANDEX_MODEL", "yandexgpt/latest")

# --- извлечение из текста ---
MAX_CHUNK_CHARS = int(os.environ.get("FACTORY_MAX_CHUNK_CHARS", "3500"))  # окно LLM
MIN_PROSE_CHARS = int(os.environ.get("FACTORY_MIN_PROSE_CHARS", "200"))  # отсев огрызков
# воркеров немного — при 4+ потоки одновременно ловят 429 и уходят в синхронный
# backoff по одному и тому же расписанию (толпа бьётся в лимит хором)
LLM_WORKERS = int(os.environ.get("FACTORY_LLM_WORKERS", "2"))            # параллельные вызовы
LLM_MAX_RETRIES = int(os.environ.get("FACTORY_LLM_RETRIES", "5"))        # backoff на 429/5xx
# после параллельного прохода фрагменты, упавшие даже после backoff внутри одного
# запроса, добираются ещё раз ПОСЛЕДОВАТЕЛЬНО (не толпой) — см. extract.py
FRAGMENT_RETRY_ATTEMPTS = int(os.environ.get("FACTORY_FRAGMENT_RETRIES", "2"))

# --- LLM-as-judge (качественная метрика ветки Б) ---
# по умолчанию — та же модель Yandex; в идеале судья ≠ генератору (см. judge.py),
# поэтому модель судьи вынесена отдельно и переопределяется через env.
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", YANDEX_MODEL)
JUDGE_CACHE = os.path.join(OUTPUTS_DIR, "judge_cache.json")

# --- Веб-поиск мировых практик (ветка «world_practice») ---
# Ищем внешнее подтверждение вмешательства в ПРОМЫШЛЕННОЙ практике обогащения.
# Тот же принцип детерминизма, что и везде: результат несёт URL + дословную цитату
# и кэшируется по отпечатку запроса → воспроизводимо и заземлено (не выдумка LLM).
WEB_SEARCH_ENABLED = os.environ.get("FACTORY_WEB", "1") not in ("0", "false", "no", "off")
WEB_SEARCH_BACKEND = os.environ.get("WEB_BACKEND", "ddg")   # ddg (без ключа) | yandex
WEB_MAX_RESULTS = int(os.environ.get("WEB_MAX_RESULTS", "8"))   # сколько ссылок тянуть на запрос
WEB_MAX_HYPS = int(os.environ.get("WEB_MAX_HYPS", "6"))        # для скольких топ-гипотез искать
WEB_FETCH_TIMEOUT = int(os.environ.get("WEB_FETCH_TIMEOUT", "12"))
WEB_PAGE_CHARS = int(os.environ.get("WEB_PAGE_CHARS", "4000"))  # сколько текста страницы в LLM
# гейт КАЧЕСТВА цитаты (поверх дословного гейта): цитата обязана быть предложением из
# основного текста, а не заголовком/названием страницы — см. websearch._quote_quality
WEB_MIN_QUOTE_CHARS = int(os.environ.get("WEB_MIN_QUOTE_CHARS", "60"))
WEB_MIN_QUOTE_WORDS = int(os.environ.get("WEB_MIN_QUOTE_WORDS", "8"))
WEB_CACHE = os.path.join(OUTPUTS_DIR, "web_cache.json")
# промышленные/материаловедческие домены — их поднимаем в выдаче (сайты вроде MITS NIMS,
# профильные журналы, вендоры оборудования). Переопределяется через env (запятыми).
WEB_INDUSTRIAL_DOMAINS = [s.strip() for s in os.environ.get(
    "WEB_DOMAINS",
    # мировые (журналы/вендоры)
    "nims.go.jp,saimm.co.za,mdpi.com,sciencedirect.com,springer.com,researchgate.net,"
    "onemine.org,metso.com,mogroup.com,ceecthefuture.org,911metallurgist.com,"
    "tandfonline.com,osti.gov,doi.org,"
    # русскоязычные — отраслевые новости/журналы/конкуренты (ближайшие соседи)
    "nornickel.ru,rudmet.ru,cyberleninka.ru,elibrary.ru,dprom.online,nedradv.ru,"
    "metalinfo.ru,metaltorg.ru,vestnik.magtu.ru,gornoe-delo.ru,zolotodb.ru,"
    "eruda.ru,mining-media.ru").split(",") if s.strip()]
# русскоязычные домены — их отдельно поднимаем, чтобы среди практик были «ближайшие
# соседи» (русские конкуренты/отрасль), а не только мировая литература
WEB_RU_DOMAINS = [s.strip() for s in os.environ.get(
    "WEB_RU_DOMAINS",
    # горные корпорации РФ (практика внедрений, а не только Норникель)
    "nornickel.ru,polymetal.ru,polyusgold.com,alrosa.ru,metalloinvest.com,"
    "uralkali.com,phosagro.ru,evraz.com,mechel.ru,rusal.ru,uralelectromed.com,"
    "ugmk.com,rmk-group.ru,acron.ru,eurochemgroup.com,"
    # отраслевые издания, вузы и научные библиотеки
    "rudmet.ru,cyberleninka.ru,elibrary.ru,dprom.online,nedradv.ru,"
    "metalinfo.ru,metaltorg.ru,vestnik.magtu.ru,gornoe-delo.ru,zolotodb.ru,"
    "eruda.ru,mining-media.ru,gornayakniga.ru,spmi.ru,misis.ru,igduran.ru").split(",") if s.strip()]

# --- OpenAlex (доказательное досье гипотезы) — НАДЁЖНЫЙ научный API, без ключа, без LLM ---
# Костяк вау-фичи: статьи + цитируемость («важность») + предложение из abstract («причина»).
# Ретрив детерминирован; заземление — реальная фраза из abstract (цитатный гейт).
OPENALEX_ENABLED = os.environ.get("FACTORY_OPENALEX", "1") not in ("0", "false", "no", "off")
OPENALEX_BASE = os.environ.get("OPENALEX_BASE", "https://api.openalex.org")
# polite pool: OpenAlex просит контактный mailto — быстрее и стабильнее (не PII фабрик)
OPENALEX_MAILTO = os.environ.get("OPENALEX_MAILTO", "hypothesis-factory@example.org")
OPENALEX_PER_HYP = int(os.environ.get("OPENALEX_PER_HYP", "3"))     # источников на гипотезу
OPENALEX_FETCH = int(os.environ.get("OPENALEX_FETCH", "12"))        # сколько тянуть перед отбором
OPENALEX_MAX_HYPS = int(os.environ.get("OPENALEX_MAX_HYPS", "6"))   # для скольких топ-гипотез
OPENALEX_CACHE = os.path.join(OUTPUTS_DIR, "openalex_cache.json")

# --- OCR (Yandex Vision) — картинки и сканы PDF → текст ---
OCR_ENABLED = os.environ.get("FACTORY_OCR", "1") not in ("0", "false", "no", "off")
OCR_BASE_URL = os.environ.get("YANDEX_OCR_URL", "https://ocr.api.cloud.yandex.net")
OCR_MODEL = os.environ.get("OCR_MODEL", "page")           # page | table | handwritten
OCR_LANGS = [s for s in os.environ.get("OCR_LANGS", "ru,en").split(",") if s]
OCR_DPI = int(os.environ.get("OCR_DPI", "200"))           # растеризация страниц PDF под OCR
OCR_MIN_CHARS = int(os.environ.get("OCR_MIN_CHARS", "8"))  # короче — считаем «пусто»
OCR_PDF_MAX_PAGES = int(os.environ.get("OCR_PDF_MAX_PAGES", "20"))  # предохранитель от скан-книг
OCR_CACHE = os.path.join(OUTPUTS_DIR, "ocr_cache.json")
# предобработка картинки ПЕРЕД OCR (Pillow) — схемы флотации ужасного качества, чистка
# поднимает распознаваемость: grayscale + автоконтраст + апскейл мелкого текста.
OCR_PREPROCESS = os.environ.get("OCR_PREPROCESS", "1") not in ("0", "false", "no", "off")
OCR_UPSCALE_MIN_PX = int(os.environ.get("OCR_UPSCALE_MIN_PX", "1400"))  # <мин.стороны → апскейл
OCR_BINARIZE = os.environ.get("OCR_BINARIZE", "0") not in ("0", "false", "no", "off")  # порог (риск)
