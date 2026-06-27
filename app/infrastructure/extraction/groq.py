"""Извлечение триплетов через OpenAI-совместимый API (по умолчанию Groq).

Конвейер extract(chunk):
  1) запрос к LLM (few-shot, structured JSON) → черновые триплеты;
  2) цитатный гейт: evidence_quote обязана быть дословной подстрокой фрагмента
     (нормализуем пробелы и регистр) — иначе триплет отбраковывается и логируется;
  3) валидация в Triplet (pydantic), привязка chunk_id/doc_id.

Кэш по chunk_id (повторно не дёргаем API), retry с экспоненциальным backoff.
Ключ берётся из GROQ_API_KEY. HTTP-клиент инжектируется (тесты подменяют его
MockTransport — без сети). Формат триплета совпадает с FakeFactExtractor.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.config import OUTPUTS_DIR, Settings, load_settings
from app.service.entities import Chunk, Triplet

logger = logging.getLogger(__name__)

_RETRY_STATUS = {429, 500, 502, 503, 504}
_WS = re.compile(r"\s+")


class _Retryable(Exception):
    """Временная ошибка провайдера (429/5xx) — имеет смысл повторить."""


def _normalize(text: str) -> str:
    """Схлопнуть пробелы и привести к нижнему регистру — для сверки цитаты."""
    return _WS.sub(" ", text).strip().lower()


def quote_is_verbatim(quote: str, text: str) -> bool:
    """Цитатный гейт: присутствует ли `quote` в `text` дословно (по нормализации)."""
    if not quote or not quote.strip():
        return False
    return _normalize(quote) in _normalize(text)


_SYSTEM_PROMPT = (
    "Ты извлекаешь факты для графа знаний R&D-центра «Норильский никель» (флотация "
    "медно-никелевых руд). Из фрагмента вытащи триплеты влияния и верни СТРОГО JSON-объект "
    'вида {"triplets": [...]}, без преамбул и markdown. Поля каждого триплета:\n'
    "  subject, object — сущности (реагент, параметр, минерал, процесс, KPI, провал);\n"
    "  relation — короткое отношение («повышает», «снижает», «приводит к», «влияет на»);\n"
    "  sign — знак влияния: \"+\" (рост), \"-\" (снижение), \"0\" (нейтрально);\n"
    "  conditions — объект условий ({} если нет);\n"
    "  outcome — \"success\" | \"failure\" | \"neutral\";\n"
    "  closure_reason — причина закрытия для провалов, иначе null;\n"
    "  evidence_quote — ДОСЛОВНАЯ подстрока фрагмента, подтверждающая факт;\n"
    "  year — год факта; если в тексте не указан, возьми год источника из заголовка [...].\n"
    "Извлекай только то, что прямо сказано в тексте. evidence_quote обязана встречаться "
    "во фрагменте буквально — не перефразируй её."
)

# few-shot: вход-фрагмент → ожидаемый JSON (цитаты — дословные подстроки)
_FEWSHOT = [
    (
        "[Источник: CMC depressant study; год: 2015]\n\n"
        "CMC addition shifts pulp pH upward, which in turn improves nickel selectivity "
        "against pyrrhotite.",
        {
            "triplets": [
                {
                    "subject": "CMC",
                    "relation": "повышает",
                    "object": "pulp pH",
                    "sign": "+",
                    "conditions": {},
                    "outcome": "neutral",
                    "closure_reason": None,
                    "evidence_quote": "CMC addition shifts pulp pH upward",
                    "year": 2015,
                },
                {
                    "subject": "pulp pH",
                    "relation": "повышает",
                    "object": "nickel selectivity",
                    "sign": "+",
                    "conditions": {},
                    "outcome": "neutral",
                    "closure_reason": None,
                    "evidence_quote": "improves nickel selectivity",
                    "year": 2015,
                },
            ]
        },
    ),
    (
        "[Источник: отчёт о НИР rep_dtp; год: 2012]\n\n"
        "Испытывали селективный дитиофосфинатный собиратель для пентландита. "
        "Исход: провал — направление закрыто. Причина закрытия: синтез слишком дорог.",
        {
            "triplets": [
                {
                    "subject": "дитиофосфинатный собиратель",
                    "relation": "приводит к",
                    "object": "закрытие направления",
                    "sign": "-",
                    "conditions": {},
                    "outcome": "failure",
                    "closure_reason": "синтез слишком дорог",
                    "evidence_quote": "Причина закрытия: синтез слишком дорог",
                    "year": 2012,
                }
            ]
        },
    ),
]


class GroqFactExtractor:
    """Реализация порта FactExtractor через OpenAI-совместимый chat-completions API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        settings: Settings | None = None,
        cache_dir: str | Path | None = None,
        max_retries: int = 4,
        backoff_base: float = 1.0,
        timeout: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        settings = settings or load_settings()
        # модель: аргумент → GROQ_MODEL (быстрый свитч без кода) → дефолт из конфига
        self.model = model or os.getenv("GROQ_MODEL") or settings.extractor_model
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self._api_key = api_key or os.getenv("GROQ_API_KEY")
        self.cache_dir = Path(cache_dir) if cache_dir else OUTPUTS_DIR / "extract_cache"
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.timeout = timeout
        self._client = client
        self._owns_client = client is None
        # счётчики и примеры отброшенного — для отчёта скрипта
        self.stats = {"extracted": 0, "dropped": 0, "cached_chunks": 0, "api_calls": 0}
        self.dropped_examples: list[dict] = []

    # --- публичный контракт ---

    def extract(self, chunk: Chunk) -> list[Triplet]:
        raw = self._cached(chunk.id)
        if raw is None:
            raw = self._call_llm(chunk.text)
            self._store_cache(chunk.id, raw)
        else:
            self.stats["cached_chunks"] += 1
        return self._to_triplets(chunk, raw)

    # --- цитатный гейт + валидация ---

    def _to_triplets(self, chunk: Chunk, raw: list[dict]) -> list[Triplet]:
        out: list[Triplet] = []
        for i, item in enumerate(raw):
            quote = str(item.get("evidence_quote", ""))
            if not quote_is_verbatim(quote, chunk.text):
                self._drop(chunk, quote, "цитата не найдена во фрагменте дословно")
                continue
            try:
                triplet = Triplet(
                    id=f"{chunk.id}#{i}",
                    chunk_id=chunk.id,
                    doc_id=chunk.doc_id,
                    subject=str(item["subject"]),
                    relation=str(item["relation"]),
                    object=str(item["object"]),
                    sign=_coerce_sign(item.get("sign")),
                    conditions=item.get("conditions") or {},
                    outcome=_coerce_outcome(item.get("outcome")),
                    closure_reason=item.get("closure_reason") or None,
                    evidence_quote=quote,
                    year=int(item["year"]),
                )
            except (KeyError, ValueError, TypeError, ValidationError) as exc:
                self._drop(chunk, quote, f"невалидный триплет: {exc}")
                continue
            out.append(triplet)
            self.stats["extracted"] += 1
        return out

    def _drop(self, chunk: Chunk, quote: str, reason: str) -> None:
        self.stats["dropped"] += 1
        logger.info("отброшен триплет [%s]: %s | цитата: %r", chunk.id, reason, quote[:80])
        if len(self.dropped_examples) < 5:
            self.dropped_examples.append(
                {"chunk_id": chunk.id, "reason": reason, "quote": quote[:120]}
            )

    # --- вызов LLM с retry/backoff ---

    def _messages(self, text: str) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for fragment, expected in _FEWSHOT:
            messages.append({"role": "user", "content": fragment})
            messages.append({"role": "assistant", "content": json.dumps(expected, ensure_ascii=False)})
        messages.append({"role": "user", "content": text})
        return messages

    def _call_llm(self, text: str) -> list[dict]:
        if not self._api_key and self._owns_client:
            raise RuntimeError("GroqFactExtractor: нет GROQ_API_KEY")
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 1500,
            "response_format": {"type": "json_object"},
            "messages": self._messages(text),
        }
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                self.stats["api_calls"] += 1
                resp = self._http().post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                if resp.status_code in _RETRY_STATUS:
                    raise _Retryable(f"HTTP {resp.status_code}")
                if resp.status_code >= 400:  # 401/403/400/404 — повтор не поможет, падаем сразу
                    raise RuntimeError(f"Groq API {resp.status_code}: {resp.text[:200]}")
                content = resp.json()["choices"][0]["message"]["content"]
                data = json.loads(content)
                triplets = data.get("triplets", []) if isinstance(data, dict) else data
                return triplets if isinstance(triplets, list) else []
            except (_Retryable, httpx.TransportError, json.JSONDecodeError, KeyError) as exc:
                last = exc
                if attempt < self.max_retries - 1:
                    delay = self.backoff_base * (2**attempt)
                    logger.warning("повтор %d/%d после ошибки: %s (пауза %.1fс)",
                                   attempt + 1, self.max_retries, exc, delay)
                    time.sleep(delay)
        raise RuntimeError(f"извлечение не удалось после {self.max_retries} попыток: {last}")

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    # --- дисковый кэш по chunk_id ---

    def _cache_path(self, chunk_id: str) -> Path:
        safe = re.sub(r"[^0-9A-Za-z_.-]", "_", chunk_id)
        return self.cache_dir / f"{safe}.json"

    def _cached(self, chunk_id: str) -> list[dict] | None:
        path = self._cache_path(chunk_id)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
        return None

    def _store_cache(self, chunk_id: str, raw: list[dict]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path(chunk_id).write_text(
            json.dumps(raw, ensure_ascii=False), encoding="utf-8"
        )


def _coerce_sign(value: object) -> str:
    return value if value in ("+", "-", "0") else "0"


def _coerce_outcome(value: object) -> str:
    return value if value in ("success", "failure", "neutral") else "neutral"


__all__ = ["GroqFactExtractor", "quote_is_verbatim"]
