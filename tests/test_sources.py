"""Оффлайн-тесты слоя данных: OpenAlex (мок HTTP) + синтетические отчёты."""

from __future__ import annotations

import httpx
import pytest

from app.infrastructure.sources.openalex import (
    OpenAlexSource,
    reconstruct_abstract,
    work_to_document,
)
from app.infrastructure.sources.synthetic_reports import (
    SCAN_REPORT_IDS,
    build_reports,
    find_recent_match,
    render_scans,
)
from app.service.entities import Document


def _inverted(text: str) -> dict[str, list[int]]:
    inv: dict[str, list[int]] = {}
    for i, w in enumerate(text.split(" ")):
        inv.setdefault(w, []).append(i)
    return inv


def _work(wid: str, title: str, year: int, abstract: str | None) -> dict:
    return {
        "id": f"https://openalex.org/{wid}",
        "title": title,
        "publication_year": year,
        "abstract_inverted_index": _inverted(abstract) if abstract else None,
        "primary_location": {"landing_page_url": f"https://doi.org/10.0/{wid}"},
    }


# --- OpenAlex ---


def test_reconstruct_abstract_orders_by_position():
    inv = {"nickel": [2], "Flotation": [0], "of": [1]}
    assert reconstruct_abstract(inv) == "Flotation of nickel"
    assert reconstruct_abstract(None) is None
    assert reconstruct_abstract({}) is None


def test_work_to_document_maps_fields_and_skips_no_abstract():
    doc = work_to_document(_work("W1", "Pentlandite flotation", 2020, "selective collector study"))
    assert doc is not None
    assert doc.id == "openalex_W1" and doc.source == "openalex"
    assert doc.year == 2020 and doc.is_synthetic is False and doc.is_scanned is False
    assert doc.text == "selective collector study"
    # без абстракта — отбраковка
    assert work_to_document(_work("W2", "No abstract", 2019, None)) is None


def test_fetch_dedupes_across_queries():
    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("search", "")
        if "copper" in q:
            results = [_work("W1", "A", 2020, "alpha"), _work("W2", "B", 2021, "beta")]
        elif "pentlandite" in q:
            results = [_work("W2", "B", 2021, "beta"), _work("W3", "C", 2018, "gamma")]
        else:
            results = []
        return httpx.Response(200, json={"results": results})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    docs = OpenAlexSource(client=client).fetch(max_docs=50)
    ids = sorted(d.id for d in docs)
    assert ids == ["openalex_W1", "openalex_W2", "openalex_W3"]  # W2 не задублирован


# --- синтетические отчёты ---


def test_build_reports_counts_and_validation():
    reports, _ = build_reports([])
    assert 15 <= len(reports) <= 20
    failures = [r for r in reports if r.outcome == "failure"]
    assert 8 <= len(failures) <= 10
    # у каждого провала есть явная причина закрытия
    assert all(r.closure_reason for r in failures)
    # всё синтетическое и валидируется сущностью Document
    docs = [r.to_document() for r in reports]
    assert all(isinstance(d, Document) and d.is_synthetic for d in docs)
    # причина закрытия попадает в текст (вход для извлечения)
    f0 = next(r for r in reports if r.outcome == "failure")
    assert "Причина закрытия" in f0.to_text()


def test_charged_pairs_form_when_fresh_fact_present():
    corpus = [
        Document(
            id="openalex_C1",
            title="Carboxymethyl cellulose depressant improves nickel selectivity",
            year=2021,
            source="openalex",
            text="CMC as depressant in copper-nickel flotation",
        ),
        Document(
            id="openalex_C2",
            title="Sodium metabisulfite depression of pyrrhotite revisited",
            year=2020,
            source="openalex",
            text="metabisulfite SMBS pyrrhotite depression",
        ),
    ]
    _, pairs = build_reports(corpus)
    assert len(pairs) >= 2
    ids = {p["failure_report_id"] for p in pairs}
    assert "rep_cmc" in ids and "rep_smbs" in ids
    cmc = next(p for p in pairs if p["failure_report_id"] == "rep_cmc")
    assert cmc["reviving_doc_id"] == "openalex_C1" and cmc["reviving_year"] == 2021


def test_find_recent_match_respects_min_year():
    old = Document(id="o", title="CMC depressant", year=2010, source="openalex", text="cmc")
    assert find_recent_match([old], ["cmc"], min_year=2017) is None


def test_render_scans_produces_image_pdfs(tmp_path):
    pytest.importorskip("PIL")
    reports, _ = build_reports([])
    scan_docs = render_scans(reports, tmp_path)
    assert len(scan_docs) == len(SCAN_REPORT_IDS)
    for d in scan_docs:
        assert d.is_scanned is True and d.text is None and d.is_synthetic is True
        assert d.source_path and (tmp_path / f"{d.id.replace('__scan', '')}.pdf").exists()
        # image-only PDF (нет текстового слоя) — начинается с PDF-сигнатуры
        assert open(d.source_path, "rb").read(4) == b"%PDF"
