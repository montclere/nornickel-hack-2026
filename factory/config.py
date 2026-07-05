from __future__ import annotations

import os


def load_env():
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

OUTPUTS_DIR = os.environ.get("FACTORY_OUTPUTS", "outputs")
DEFAULT_CACHE = os.path.join(OUTPUTS_DIR, "kb_cache.json")

RUN_CONFIG_PATH = os.path.join(OUTPUTS_DIR, "last_run.json")

SECONDARY_MIN_SHARE = float(os.environ.get("FACTORY_SECONDARY_SHARE", "0.30"))

FEEDBACK_PATH = os.environ.get("FACTORY_FEEDBACK_PATH",
                               os.path.join(OUTPUTS_DIR, "feedback.json"))
FEEDBACK_ENABLED = os.environ.get("FACTORY_FEEDBACK", "1") not in ("0", "false", "no", "off")

YANDEX_BASE_URL = os.environ.get(
    "YANDEX_BASE_URL", "https://llm.api.cloud.yandex.net/foundationModels/v1")
YANDEX_MODEL = os.environ.get("YANDEX_MODEL", "yandexgpt/latest")

MAX_CHUNK_CHARS = int(os.environ.get("FACTORY_MAX_CHUNK_CHARS", "3500"))
MIN_PROSE_CHARS = int(os.environ.get("FACTORY_MIN_PROSE_CHARS", "200"))

LLM_WORKERS = int(os.environ.get("FACTORY_LLM_WORKERS", "2"))
LLM_MAX_RETRIES = int(os.environ.get("FACTORY_LLM_RETRIES", "5"))

FRAGMENT_RETRY_ATTEMPTS = int(os.environ.get("FACTORY_FRAGMENT_RETRIES", "2"))

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", YANDEX_MODEL)
JUDGE_CACHE = os.path.join(OUTPUTS_DIR, "judge_cache.json")

WEB_SEARCH_ENABLED = os.environ.get("FACTORY_WEB", "1") not in ("0", "false", "no", "off")
WEB_SEARCH_BACKEND = os.environ.get("WEB_BACKEND", "ddg")
WEB_MAX_RESULTS = int(os.environ.get("WEB_MAX_RESULTS", "8"))
WEB_MAX_HYPS = int(os.environ.get("WEB_MAX_HYPS", "6"))
WEB_FETCH_TIMEOUT = int(os.environ.get("WEB_FETCH_TIMEOUT", "6"))

WEB_FETCH_WORKERS = int(os.environ.get("WEB_FETCH_WORKERS", "8"))
WEB_HYP_WORKERS = int(os.environ.get("WEB_HYP_WORKERS", "3"))
WEB_PER_DOMAIN = int(os.environ.get("WEB_PER_DOMAIN", "2"))
WEB_PAGE_CHARS = int(os.environ.get("WEB_PAGE_CHARS", "4000"))

WEB_MIN_QUOTE_CHARS = int(os.environ.get("WEB_MIN_QUOTE_CHARS", "60"))
WEB_MIN_QUOTE_WORDS = int(os.environ.get("WEB_MIN_QUOTE_WORDS", "8"))
WEB_CACHE = os.path.join(OUTPUTS_DIR, "web_cache.json")

WEB_INDUSTRIAL_DOMAINS = [s.strip() for s in os.environ.get(
    "WEB_DOMAINS",

    "nims.go.jp,saimm.co.za,mdpi.com,sciencedirect.com,springer.com,researchgate.net,"
    "onemine.org,metso.com,mogroup.com,ceecthefuture.org,911metallurgist.com,"
    "tandfonline.com,osti.gov,doi.org,"

    "nornickel.ru,rudmet.ru,cyberleninka.ru,elibrary.ru,dprom.online,nedradv.ru,"
    "metalinfo.ru,metaltorg.ru,vestnik.magtu.ru,gornoe-delo.ru,zolotodb.ru,"
    "eruda.ru,mining-media.ru").split(",") if s.strip()]

WEB_RU_DOMAINS = [s.strip() for s in os.environ.get(
    "WEB_RU_DOMAINS",

    "nornickel.ru,polymetal.ru,polyusgold.com,alrosa.ru,metalloinvest.com,"
    "uralkali.com,phosagro.ru,evraz.com,mechel.ru,rusal.ru,uralelectromed.com,"
    "ugmk.com,rmk-group.ru,acron.ru,eurochemgroup.com,"

    "rudmet.ru,cyberleninka.ru,elibrary.ru,dprom.online,nedradv.ru,"
    "metalinfo.ru,metaltorg.ru,vestnik.magtu.ru,gornoe-delo.ru,zolotodb.ru,"
    "eruda.ru,mining-media.ru,gornayakniga.ru,spmi.ru,misis.ru,igduran.ru").split(",") if s.strip()]

OPENALEX_ENABLED = os.environ.get("FACTORY_OPENALEX", "1") not in ("0", "false", "no", "off")
OPENALEX_BASE = os.environ.get("OPENALEX_BASE", "https://api.openalex.org")

OPENALEX_MAILTO = os.environ.get("OPENALEX_MAILTO", "hypothesis-factory@example.org")
OPENALEX_PER_HYP = int(os.environ.get("OPENALEX_PER_HYP", "3"))
OPENALEX_FETCH = int(os.environ.get("OPENALEX_FETCH", "12"))
OPENALEX_MAX_HYPS = int(os.environ.get("OPENALEX_MAX_HYPS", "6"))
OPENALEX_CACHE = os.path.join(OUTPUTS_DIR, "openalex_cache.json")

OCR_ENABLED = os.environ.get("FACTORY_OCR", "1") not in ("0", "false", "no", "off")
OCR_BASE_URL = os.environ.get("YANDEX_OCR_URL", "https://ocr.api.cloud.yandex.net")
OCR_MODEL = os.environ.get("OCR_MODEL", "page")
OCR_LANGS = [s for s in os.environ.get("OCR_LANGS", "ru,en").split(",") if s]
OCR_DPI = int(os.environ.get("OCR_DPI", "200"))
OCR_MIN_CHARS = int(os.environ.get("OCR_MIN_CHARS", "8"))
OCR_PDF_MAX_PAGES = int(os.environ.get("OCR_PDF_MAX_PAGES", "20"))
OCR_CACHE = os.path.join(OUTPUTS_DIR, "ocr_cache.json")

OCR_PREPROCESS = os.environ.get("OCR_PREPROCESS", "1") not in ("0", "false", "no", "off")
OCR_UPSCALE_MIN_PX = int(os.environ.get("OCR_UPSCALE_MIN_PX", "1400"))
OCR_BINARIZE = os.environ.get("OCR_BINARIZE", "0") not in ("0", "false", "no", "off")
