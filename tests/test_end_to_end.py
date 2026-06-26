"""build('fake') собирает use-cases, прогоняемые end-to-end на фикстурах.

Без сети и GPU: весь конвейер бежит на fake-инфраструктуре и фикстурах.
"""

from __future__ import annotations

from app.container import Container, build
from app.service.entities import (
    AgentResult,
    Document,
    Edge,
    Feedback,
    GraphSnapshot,
    Node,
    Triplet,
)
from tests.conftest import load_fixture

KPI = "извлечение Ni +2%"


def test_build_fake_returns_all_usecases():
    c = build("fake")
    assert isinstance(c, Container)
    for name in (
        "build_knowledge_base",
        "enrich_graph",
        "generate_hypotheses",
        "submit_feedback",
        "chat",
    ):
        assert hasattr(c, name)


def test_build_real_offline_safe(monkeypatch):
    # real-режим оффлайн-запускаем: real там, где реализовано, иначе fake
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = build("real")
    modes = c.adapter_modes
    assert modes["persistence"].startswith("SQLite")  # персист — всегда оффлайн-real
    assert modes["ocr"].startswith("fake")  # Unlimited-OCR ещё не готов → fake
    assert modes["phrasing"].startswith("fake")  # нет ключа → fake


def test_ocr_switchable_via_config(monkeypatch):
    # PHOENIX_OCR=fake форсит fake-OCR даже в real-режиме — без правок кода
    monkeypatch.setenv("PHOENIX_OCR", "fake")
    assert build("real").adapter_modes["ocr"] == "fake"


def test_ingest_runs_through_fakes_including_ocr():
    c = build("fake")
    docs = [Document(**d) for d in load_fixture("documents.json")]
    triplets = c.build_knowledge_base.execute(docs)
    assert triplets and all(isinstance(t, Triplet) for t in triplets)
    # скан report_2012 прошёл через OCR-путь и тоже дал триплет
    assert any(t.doc_id == "report_2012" for t in triplets)


def test_enrich_graph_freezes_snapshot():
    c = build("fake")
    snap = c.enrich_graph.execute(KPI)
    assert isinstance(snap, GraphSnapshot)
    assert snap.triplet_count >= 1
    # snapshot_id детерминирован
    assert snap.snapshot_id == c.enrich_graph.execute(KPI).snapshot_id


def test_generate_returns_list():
    c = build("fake")
    # пустой граф → пусто (генераторам нужны узлы/рёбра)
    assert c.generate_hypotheses.execute(KPI) == []

    # на засеянном графе генераторы дают карточки с origin и graveyard_check
    c.graph_repository.add_nodes([Node(**n) for n in load_fixture("nodes.json")])
    c.graph_repository.add_edges([Edge(**e) for e in load_fixture("edges.json")])
    hyps = c.generate_hypotheses.execute(KPI)
    assert hyps and isinstance(hyps, list)
    assert {h.origin for h in hyps} == {"gap", "reanimation", "contradiction"}
    assert all(h.graveyard_check is not None for h in hyps)


def test_submit_feedback_returns_weights():
    c = build("fake")
    weights = c.submit_feedback.execute(Feedback(**load_fixture("feedback.json")))
    assert isinstance(weights, dict) and weights


def test_chat_is_read_only():
    c = build("fake")
    # заполняем граф фикстурами
    c.graph_repository.add_nodes([Node(**n) for n in load_fixture("nodes.json")])
    c.graph_repository.add_edges([Edge(**e) for e in load_fixture("edges.json")])
    edges_before = len(c.graph_repository.edges)  # type: ignore[attr-defined]
    nodes_before = len(c.graph_repository.nodes)  # type: ignore[attr-defined]

    res = c.chat.execute("почему коллектор X отклонили в 2012?")
    assert isinstance(res, AgentResult)
    assert res.answer and res.sources

    # READ-ONLY: чат не изменил граф
    assert len(c.graph_repository.edges) == edges_before  # type: ignore[attr-defined]
    assert len(c.graph_repository.nodes) == nodes_before  # type: ignore[attr-defined]


def test_full_pipeline_smoke():
    """Один проход всего конвейера на фикстурах без падений."""
    c = build("fake")

    docs = [Document(**d) for d in load_fixture("documents.json")]
    assert c.build_knowledge_base.execute(docs)

    snap = c.enrich_graph.execute(KPI)
    assert snap.snapshot_id

    c.graph_repository.add_nodes([Node(**n) for n in load_fixture("nodes.json")])
    c.graph_repository.add_edges([Edge(**e) for e in load_fixture("edges.json")])
    assert c.generate_hypotheses.execute(KPI)  # генераторы дают непустой список

    assert c.chat.execute("вопрос?").answer
    assert c.submit_feedback.execute(Feedback(**load_fixture("feedback.json")))
