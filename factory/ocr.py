# -*- coding: utf-8 -*-
"""OCR через Yandex Vision — картинки и сканы в текст. Всё на стеке Yandex.

Тот же ключ, что и у LLM (YANDEX_API_KEY + YANDEX_FOLDER_ID), общий транспорт с
backoff (llm.post_json). YandexGPT текстовый (изображения на вход не принимает),
поэтому «понимание» картинки = OCR-текст, который дальше идёт в ту же ветку Б
(extract → граф → discover → judge).

Результат кэшируется по хэшу байтов изображения → повторный приём не перераспознаёт
(OCR медленный и платный). Для схем-диаграмм OCR даёт подписи узлов; связи из них
восстанавливает уже текстовый YandexGPT в extract.py.

Важно: Vision OCR — ОТДЕЛЬНЫЙ сервис Yandex Cloud (ocr.api.cloud.yandex.net), не
AI Studio. Ключу нужны права на OCR (роль ai.vision.user); иначе будет 401/403.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os

from factory.client import post_json
from factory.config import OCR_BASE_URL, OCR_CACHE, OCR_LANGS, OCR_MODEL, load_env


def _extract_text(d) -> str:
    """Достать текст из ответа recognizeText: fullText, иначе собрать из блоков/строк."""
    ann = ((d or {}).get("result") or {}).get("textAnnotation") or {}
    full = (ann.get("fullText") or "").strip()
    if full:
        return full
    lines = []
    for b in ann.get("blocks") or []:
        for ln in b.get("lines") or []:
            t = (ln.get("text") or "").strip()
            if t:
                lines.append(t)
    return "\n".join(lines)


class YandexOCR:
    """Клиент Yandex Vision OCR (recognizeText) с кэшем по хэшу изображения."""

    def __init__(self, model=OCR_MODEL, langs=None, cache_path=OCR_CACHE):
        load_env()
        self.key = os.environ.get("YANDEX_API_KEY")
        self.folder = os.environ.get("YANDEX_FOLDER_ID")
        self.model = model
        self.langs = langs or list(OCR_LANGS)
        self.cache_path = cache_path
        self.cache = {}
        if cache_path and os.path.exists(cache_path):
            try:
                self.cache = json.load(open(cache_path, encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.cache = {}

    @property
    def ready(self):
        return bool(self.key and self.folder)

    def probe(self, timeout=6) -> bool:
        """Быстрый чек РЕАЛЬНОЙ доступности OCR (не только наличия ключа): крошечная
        картинка, короткий таймаут, БЕЗ ретраев. Любая ошибка/зависание → False, чтобы
        приём материалов не висел минутами на мёртвом OCR-эндпоинте."""
        if not self.ready:
            return False
        try:
            import io
            from PIL import Image
            buf = io.BytesIO(); Image.new("L", (32, 32), 255).save(buf, format="PNG")
            data = buf.getvalue()
        except Exception:  # noqa: BLE001
            data = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
        try:
            post_json(f"{OCR_BASE_URL}/ocr/v1/recognizeText",
                      {"mimeType": "image/png", "languageCodes": self.langs,
                       "model": self.model, "content": base64.b64encode(data).decode("ascii")},
                      {"Authorization": f"Api-Key {self.key}", "x-folder-id": self.folder},
                      timeout, source="ocr", max_retries=0)
            return True
        except Exception:  # noqa: BLE001
            return False

    def recognize(self, data: bytes, mime="image/png", timeout=60) -> str:
        """bytes изображения → распознанный текст (с кэшем). '' при пустом результате.
        Перед распознаванием чистим картинку (imageprep) — сканы схем очень шумные."""
        from factory.imageprep import preprocess, preprocess_tag
        # ключ кэша — по ИСХОДНЫМ байтам + политике предобработки (сменили политику →
        # перераспознаём), но в OCR уходит уже очищенная картинка (всегда PNG)
        key = (hashlib.sha256(data).hexdigest()[:16]
               + f":{self.model}:{','.join(self.langs)}:{preprocess_tag()}")
        if key in self.cache:
            return self.cache[key]
        clean = preprocess(data)
        if clean is not data:
            mime = "image/png"                     # imageprep всегда отдаёт PNG
        payload = {"mimeType": mime, "languageCodes": self.langs, "model": self.model,
                   "content": base64.b64encode(clean).decode("ascii")}
        headers = {"Authorization": f"Api-Key {self.key}", "x-folder-id": self.folder}
        d = post_json(f"{OCR_BASE_URL}/ocr/v1/recognizeText", payload, headers, timeout, source="ocr")
        text = _extract_text(d)
        self.cache[key] = text
        self._flush()
        return text

    def _flush(self):
        if not self.cache_path:
            return
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        json.dump(self.cache, open(self.cache_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
