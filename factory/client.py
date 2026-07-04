# -*- coding: utf-8 -*-
"""Единая точка ВСЕХ внешних вызовов (LLM, OCR, OpenAlex, веб) + телеметрия.

Зачем одно место: одинаковая политика ретраев/backoff/джиттера, предохранитель
(circuit-breaker — не долбить мёртвый источник), единый учёт метрик (вызовы, ретраи,
задержки, токены, ошибки). Это «инфа про работу системы» — и бизнес, и dev.

Сеть синхронная (urllib) — намеренно просто и без внешних зависимостей; переход на
async — отдельный шаг перед сервисом (см. PLAN). Токены LLM берём из ответа Yandex
(`result.usage`), где они есть.

Приватность: сюда сходятся ВСЕ исходящие запросы — удобная единственная граница, за
которой видно, что и куда уходит (данные фабрик наружу не отправляются — только термины
запроса к подтверждённым источникам).
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from factory.config import LLM_MAX_RETRIES

_RETRY_CODES = {429, 500, 502, 503, 504}
_UA = ("Mozilla/5.0 (compatible; HypothesisFactory/1.0; +https://example.org/bot)")

# circuit-breaker: после N подряд ошибок по источнику — короткая пауза, во время которой
# вызовы к этому источнику падают сразу (не ждём таймаут каждый раз)
# порог повыше: батч-обогащение (досье/практики) не должно глохнуть из-за пары
# транзиентных 429/таймаутов — предохранитель только против ДОЛГО мёртвого источника
_BREAKER_THRESHOLD = 10
_BREAKER_COOLDOWN = 20.0


class CircuitOpen(RuntimeError):
    """Источник временно «выключен» предохранителем — слишком много подряд ошибок."""


@dataclass
class SourceStat:
    calls: int = 0
    retries: int = 0
    errors: int = 0
    latency_ms: float = 0.0
    bytes_in: int = 0
    tokens_in: int = 0
    tokens_out: int = 0

    def as_dict(self):
        avg = round(self.latency_ms / self.calls, 1) if self.calls else 0.0
        return {"calls": self.calls, "retries": self.retries, "errors": self.errors,
                "avg_latency_ms": avg, "total_latency_ms": round(self.latency_ms, 1),
                "bytes_in": self.bytes_in, "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out}


class Telemetry:
    """Потокобезопасный сбор метрик по источникам (llm/ocr/openalex/web)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stats: dict[str, SourceStat] = {}
        self._t0 = time.time()

    def record(self, source, latency_ms=0.0, retries=0, error=False, bytes_in=0):
        with self._lock:
            s = self._stats.setdefault(source, SourceStat())
            s.calls += 1
            s.retries += retries
            s.errors += int(error)
            s.latency_ms += latency_ms
            s.bytes_in += bytes_in

    def add_tokens(self, source, tokens_in=0, tokens_out=0):
        """Токены отдельно — НЕ инкрементит счётчик вызовов (вызов уже учтён в record)."""
        with self._lock:
            s = self._stats.setdefault(source, SourceStat())
            s.tokens_in += tokens_in; s.tokens_out += tokens_out

    def snapshot(self) -> dict:
        with self._lock:
            per = {k: v.as_dict() for k, v in self._stats.items()}
        tot = {"calls": sum(v["calls"] for v in per.values()),
               "retries": sum(v["retries"] for v in per.values()),
               "errors": sum(v["errors"] for v in per.values()),
               "tokens_in": sum(v["tokens_in"] for v in per.values()),
               "tokens_out": sum(v["tokens_out"] for v in per.values())}
        return {"wall_seconds": round(time.time() - self._t0, 1),
                "by_source": per, "total": tot}

    def dump(self, path):
        import os
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        json.dump(self.snapshot(), open(path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        return path

    def reset(self):
        with self._lock:
            self._stats.clear(); self._t0 = time.time()


TELEMETRY = Telemetry()


class _Breaker:
    def __init__(self):
        self._lock = threading.Lock()
        self._fails: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

    def check(self, source):
        with self._lock:
            until = self._open_until.get(source, 0)
            if until and time.time() < until:
                raise CircuitOpen(f"источник «{source}» временно отключён предохранителем "
                                  f"(ещё {until - time.time():.0f} c)")

    def ok(self, source):
        with self._lock:
            self._fails[source] = 0; self._open_until.pop(source, None)

    def fail(self, source):
        with self._lock:
            self._fails[source] = self._fails.get(source, 0) + 1
            if self._fails[source] >= _BREAKER_THRESHOLD:
                self._open_until[source] = time.time() + _BREAKER_COOLDOWN


_BREAKER = _Breaker()


def _retry_after(err):
    try:
        return float(err.headers.get("Retry-After"))
    except (TypeError, ValueError, AttributeError):
        return None


def request(url, *, source, method="GET", data=None, headers=None, timeout=30,
            max_retries=LLM_MAX_RETRIES, parse="json", max_bytes=None, accept_types=None):
    """Единый исходящий запрос с ретраями/backoff/джиттером, предохранителем и телеметрией.

    parse: "json" | "text" | "bytes". Бросает исключение после исчерпания ретраев или
    сразу, если по источнику открыт предохранитель (CircuitOpen)."""
    import random
    _BREAKER.check(source)
    hdrs = {"User-Agent": _UA, **(headers or {})}
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)

    t0 = time.time(); last = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                # accept_types: чужой Content-Type (например application/pdf при
                # ожидании text/html) → не читаем тело вовсе, экономим десятки секунд
                if accept_types and not str(r.headers.get_content_type() or "")\
                        .startswith(tuple(accept_types)):
                    TELEMETRY.record(source, latency_ms=(time.time()-t0)*1000, retries=attempt)
                    _BREAKER.ok(source)
                    return "" if parse == "text" else (b"" if parse == "bytes" else {})
                raw = r.read(max_bytes) if max_bytes else r.read()
            dt = (time.time() - t0) * 1000
            out = (json.loads(raw.decode("utf-8")) if parse == "json"
                   else raw.decode(r.headers.get_content_charset() or "utf-8", "ignore")
                   if parse == "text" else raw)
            TELEMETRY.record(source, latency_ms=dt, retries=attempt, bytes_in=len(raw))
            _BREAKER.ok(source)
            return out
        except urllib.error.HTTPError as e:
            if e.code not in _RETRY_CODES or attempt == max_retries:
                TELEMETRY.record(source, latency_ms=(time.time()-t0)*1000,
                                 retries=attempt, error=True)
                _BREAKER.fail(source); raise
            base = _retry_after(e) or min(2 ** attempt, 30); last = e
        except urllib.error.URLError as e:
            if attempt == max_retries:
                TELEMETRY.record(source, latency_ms=(time.time()-t0)*1000,
                                 retries=attempt, error=True)
                _BREAKER.fail(source); raise
            base = min(2 ** attempt, 30); last = e
        # джиттер: параллельные воркеры не должны просыпаться синхронно и снова бить в лимит
        time.sleep(base + random.uniform(0, base * 0.5 + 0.5))
    _BREAKER.fail(source); raise last              # недостижимо, но явно


def post_json(url, payload, headers=None, timeout=90, source="llm", max_retries=LLM_MAX_RETRIES):
    """POST JSON. Общий транспорт для сервисов Yandex (LLM/эмбеддинги/OCR)."""
    return request(url, source=source, method="POST", data=payload, headers=headers,
                   timeout=timeout, max_retries=max_retries, parse="json")


def get_json(url, headers=None, timeout=30, source="http", max_retries=3):
    return request(url, source=source, headers=headers, timeout=timeout,
                   max_retries=max_retries, parse="json")


def get_text(url, headers=None, timeout=30, source="http", max_retries=2,
             max_bytes=None, accept_types=None):
    return request(url, source=source, headers=headers, timeout=timeout,
                   max_retries=max_retries, parse="text", max_bytes=max_bytes,
                   accept_types=accept_types)


def record_tokens(source, resp):
    """Достать токены из ответа Yandex (result.usage), если есть, и учесть в телеметрии."""
    try:
        u = (resp.get("result") or {}).get("usage") or {}
        ti = int(u.get("inputTextTokens", 0)); to = int(u.get("completionTokens", 0))
        if ti or to:
            TELEMETRY.add_tokens(source, tokens_in=ti, tokens_out=to)
    except (AttributeError, TypeError, ValueError):
        pass
