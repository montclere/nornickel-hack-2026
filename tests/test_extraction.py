"""Оффлайн-тесты извлечения фактов (GroqFactExtractor) — без сети, через MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from app.container import build
from app.infrastructure.extraction import GroqFactExtractor, quote_is_verbatim
from app.service.entities import Chunk

CHUNK_TEXT = (
    "[Источник: CMC study; год: 2015]\n\n"
    "CMC addition shifts pulp pH upward and improves nickel selectivity."
)


def _chunk() -> Chunk:
    return Chunk(id="doc1::0", doc_id="doc1", text=CHUNK_TEXT, position=0)


def _completion(triplets: list[dict]) -> dict:
    """Groq-style chat completion с JSON-объектом в content."""
    content = json.dumps({"triplets": triplets}, ensure_ascii=False)
    return {"choices": [{"message": {"content": content}}]}


def _extractor(handler, tmp_path, **kw) -> GroqFactExtractor:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GroqFactExtractor(api_key="test", client=client, cache_dir=tmp_path, **kw)


# --- цитатный гейт (чистая функция) ---


def test_quote_is_verbatim_normalizes_whitespace_and_case():
    assert quote_is_verbatim("CMC addition shifts pulp pH upward", CHUNK_TEXT)
    assert quote_is_verbatim("cmc   ADDITION shifts   pulp pH upward", CHUNK_TEXT)  # пробелы/регистр
    assert not quote_is_verbatim("this was never written", CHUNK_TEXT)
    assert not quote_is_verbatim("", CHUNK_TEXT)


# --- фильтр галлюцинаций в конвейере ---


def test_extract_drops_hallucinated_quote(tmp_path):
    triplets = [
        {  # обоснован — цитата дословна
            "subject": "CMC", "relation": "повышает", "object": "pulp pH", "sign": "+",
            "conditions": {}, "outcome": "neutral", "closure_reason": None,
            "evidence_quote": "CMC addition shifts pulp pH upward", "year": 2015,
        },
        {  # галлюцинация — цитаты нет во фрагменте
            "subject": "X", "relation": "y", "object": "z", "sign": "+",
            "conditions": {}, "outcome": "neutral", "closure_reason": None,
            "evidence_quote": "totally fabricated sentence", "year": 2015,
        },
    ]
    ext = _extractor(lambda r: httpx.Response(200, json=_completion(triplets)), tmp_path)
    out = ext.extract(_chunk())
    assert len(out) == 1  # галлюцинация отброшена
    assert out[0].subject == "CMC"
    assert out[0].chunk_id == "doc1::0" and out[0].doc_id == "doc1"
    assert ext.stats["extracted"] == 1 and ext.stats["dropped"] == 1
    assert ext.dropped_examples and "не найдена" in ext.dropped_examples[0]["reason"]


def test_extract_coerces_bad_sign_and_outcome(tmp_path):
    triplets = [{
        "subject": "CMC", "relation": "повышает", "object": "nickel selectivity",
        "sign": "ПЛЮС", "outcome": "weird", "conditions": {}, "closure_reason": None,
        "evidence_quote": "improves nickel selectivity", "year": 2015,
    }]
    ext = _extractor(lambda r: httpx.Response(200, json=_completion(triplets)), tmp_path)
    out = ext.extract(_chunk())
    assert len(out) == 1
    assert out[0].sign == "0" and out[0].outcome == "neutral"  # некорректные значения приведены


def test_extract_drops_invalid_triplet_missing_year(tmp_path):
    triplets = [{
        "subject": "CMC", "relation": "повышает", "object": "pulp pH", "sign": "+",
        "conditions": {}, "outcome": "neutral", "closure_reason": None,
        "evidence_quote": "CMC addition shifts pulp pH upward",  # year отсутствует
    }]
    ext = _extractor(lambda r: httpx.Response(200, json=_completion(triplets)), tmp_path)
    assert ext.extract(_chunk()) == []
    assert ext.stats["dropped"] == 1


# --- кэш по chunk_id ---


def test_cache_avoids_second_api_call(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        triplets = [{
            "subject": "CMC", "relation": "повышает", "object": "pulp pH", "sign": "+",
            "conditions": {}, "outcome": "neutral", "closure_reason": None,
            "evidence_quote": "CMC addition shifts pulp pH upward", "year": 2015,
        }]
        return httpx.Response(200, json=_completion(triplets))

    ext = _extractor(handler, tmp_path)
    ext.extract(_chunk())
    ext.extract(_chunk())  # тот же chunk_id → из кэша
    assert calls["n"] == 1
    assert ext.stats["cached_chunks"] == 1


def test_retries_then_succeeds(tmp_path):
    seq = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seq["n"] += 1
        if seq["n"] == 1:
            return httpx.Response(503, json={"error": "overloaded"})  # ретраебельно
        triplets = [{
            "subject": "CMC", "relation": "повышает", "object": "pulp pH", "sign": "+",
            "conditions": {}, "outcome": "neutral", "closure_reason": None,
            "evidence_quote": "CMC addition shifts pulp pH upward", "year": 2015,
        }]
        return httpx.Response(200, json=_completion(triplets))

    ext = _extractor(handler, tmp_path, backoff_base=0.0)  # без пауз в тесте
    out = ext.extract(_chunk())
    assert len(out) == 1 and seq["n"] == 2


def test_no_retry_on_auth_error(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})

    ext = _extractor(handler, tmp_path, backoff_base=0.0)
    with pytest.raises(RuntimeError):
        ext.extract(_chunk())
    assert calls["n"] == 1  # 401 не ретраится — падаем сразу


# --- переключение в контейнере ---


def test_container_falls_back_to_fake_without_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    c = build("real", db_path=":memory:")
    assert c.adapter_modes["extractor"].startswith("fake")


def test_container_uses_real_with_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    c = build("real", db_path=":memory:")
    assert c.adapter_modes["extractor"] == "real"  # инстанс создан, без вызовов API
    assert isinstance(c.build_knowledge_base.fact_extractor, GroqFactExtractor)


def test_fake_extractor_offline(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    c = build("fake", db_path=":memory:")
    assert c.adapter_modes["extractor"] == "fake"
    # фейк отдаёт триплеты из фикстур по doc_id — оффлайн, без сети
    triplets = c.build_knowledge_base.fact_extractor.extract(
        Chunk(id="failure_collector_X_2012::0", doc_id="report_2012", text="x", position=0)
    )
    assert isinstance(triplets, list)
