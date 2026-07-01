"""Fake-адаптеры детерминированны, валидны и реализуют контракт портов."""

from __future__ import annotations

from app.infrastructure.fakes import (
    FakeCardPhrasing,
    FakeFactExtractor,
    FakeGraphRepository,
    FakeOcr,
    FakeResearchAgent,
)
from app.service.entities import (
    AgentResult,
    Chunk,
    Edge,
    Node,
    ParsedDocument,
    PhrasedCard,
    Triplet,
)
from app.service.interfaces import (
    CardPhrasing,
    FactExtractor,
    GraphRepository,
    Ocr,
    ResearchAgent,
)


def test_fakes_satisfy_protocols():
    # runtime_checkable Protocol — structural check
    assert isinstance(FakeOcr(), Ocr)
    assert isinstance(FakeFactExtractor(), FactExtractor)
    assert isinstance(FakeCardPhrasing(), CardPhrasing)
    assert isinstance(FakeGraphRepository(), GraphRepository)
    assert isinstance(FakeResearchAgent(), ResearchAgent)


def test_fake_ocr_returns_parsed_document(tmp_path):
    parsed = FakeOcr().parse(tmp_path / "report_2012.pdf")
    assert isinstance(parsed, ParsedDocument)
    assert parsed.markdown


def test_fake_ocr_prefers_sidecar(tmp_path):
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(b"%PDF-fake")
    (tmp_path / "scan.pdf.txt").write_text("# из sidecar", encoding="utf-8")
    parsed = FakeOcr().parse(scan)
    assert parsed.markdown == "# из sidecar"
    assert parsed.meta["source"] == "sidecar"


def test_fake_extractor_matches_by_doc_id():
    extractor = FakeFactExtractor()
    chunk = Chunk(id="report_2011::0", doc_id="report_2011", text="...", position=0)
    triplets = extractor.extract(chunk)
    assert triplets and all(isinstance(t, Triplet) for t in triplets)
    # chunk_id переписан на реальный фрагмент
    assert all(t.chunk_id == "report_2011::0" for t in triplets)
    # неизвестный doc_id → пусто
    assert extractor.extract(Chunk(id="x::0", doc_id="unknown", text="", position=0)) == []


def test_fake_extractor_is_deterministic():
    a = FakeFactExtractor().extract(
        Chunk(id="report_2009::0", doc_id="report_2009", text="t", position=0)
    )
    b = FakeFactExtractor().extract(
        Chunk(id="report_2009::0", doc_id="report_2009", text="t", position=0)
    )
    assert [t.model_dump() for t in a] == [t.model_dump() for t in b]


def test_fake_card_phrasing():
    card = FakeCardPhrasing().phrase(
        {"subject": "коллектор X", "target": "извлечение Ni", "mechanism": "адсорбция"}
    )
    assert isinstance(card, PhrasedCard)
    assert "коллектор X" in card.if_ and card.because == "адсорбция"


def test_fake_graph_repo_queries():
    repo = FakeGraphRepository()
    repo.add_nodes(
        [
            Node(id="A", label="A", type="reagent"),
            Node(id="B", label="B", type="parameter"),
            Node(id="C", label="C", type="KPI"),
            Node(id="F", label="fail", type="failure", closure_reason="дорого"),
        ]
    )
    repo.add_edges(
        [
            Edge(source="A", target="B", sign="+", doc_id="d1", evidence_quote="q", year=2010),
            Edge(source="B", target="C", sign="+", doc_id="d2", evidence_quote="q", year=2011),
            Edge(source="A", target="C", sign="+", doc_id="d3", evidence_quote="q", year=2009),
            Edge(source="A", target="C", sign="-", doc_id="d4", evidence_quote="q", year=2019),
        ]
    )
    # путь A→B→C существует
    paths = repo.query_paths("A", "C", max_len=3)
    assert any(len(p) == 2 for p in paths)
    # конфликт A→C (+ vs -)
    conflicts = repo.conflicting_edges()
    assert len(conflicts) == 1
    # провал отдельным типом
    assert [n.id for n in repo.failure_nodes()] == ["F"]
    # соседи A
    assert {n.id for n in repo.neighbors("A")} == {"B", "C"}


def test_fake_graph_repo_save_load(tmp_path):
    repo = FakeGraphRepository()
    repo.add_nodes([Node(id="A", label="A", type="reagent")])
    repo.add_edges(
        [Edge(source="A", target="B", sign="+", doc_id="d", evidence_quote="q", year=2010)]
    )
    path = tmp_path / "graph.json"
    repo.save(path)
    restored = FakeGraphRepository()
    restored.load(path)
    assert [n.model_dump() for n in restored.nodes] == [n.model_dump() for n in repo.nodes]
    assert [e.model_dump() for e in restored.edges] == [e.model_dump() for e in repo.edges]


def test_fake_research_agent_modes():
    scout = FakeResearchAgent().run("scout", {"kpi": "Ni"})
    assert isinstance(scout, AgentResult)
    assert scout.mission == "scout" and scout.triplets and scout.trace.steps

    chat = FakeResearchAgent().run("chat", {"question": "почему?"})
    assert chat.mission == "chat" and chat.answer and chat.sources
