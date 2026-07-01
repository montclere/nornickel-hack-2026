"""Оффлайн-тесты агента-разведчика: шаги, добыча триплета, бюджет, перезаморозка снапшота.

Без сети и LLM: источник и экстрактор — фейковые, use_llm=False (детерминированный план).
"""

from __future__ import annotations

import pytest

from app.service.domain.graph_ops import graph_snapshot_id
from app.service.entities import AgentResult, AgentTrace, Document, Edge, Node, Triplet

pytest.importorskip("langgraph")
pytest.importorskip("networkx")
from app.infrastructure.agent import LangGraphResearchAgent  # noqa: E402
from app.infrastructure.graph import NetworkxGraphRepository  # noqa: E402
from app.service.pipeline import EnrichGraph  # noqa: E402


class FakeSource:
    """Источник литературы: отдаёт фиксированный список статей на любой запрос."""

    def __init__(self, docs: list[Document]) -> None:
        self.docs = docs

    def search(self, query: str, *, limit: int = 4) -> list[Document]:
        return self.docs[:limit]


class CountingSource:
    """Каждый запрос — новая уникальная статья (покрытие растёт, стоп только по бюджету)."""

    def __init__(self) -> None:
        self.n = 0

    def search(self, query: str, *, limit: int = 4) -> list[Document]:
        self.n += 1
        return [Document(id=f"openalex_{self.n}", title=f"paper {self.n}", year=2020,
                         source="openalex", text="text")]


class StubExtractor:
    """Возвращает по одному цитированному триплету на документ (гейт уже пройден в Промпте 2)."""

    def extract(self, chunk):
        return [Triplet(
            id=f"{chunk.id}", chunk_id=chunk.id, doc_id=chunk.doc_id,
            subject="CMC", relation="повышает", object="извлечение Ni", sign="+",
            evidence_quote="cmc improves nickel recovery", year=2020,
        )]


def _kpi_graph() -> NetworkxGraphRepository:
    repo = NetworkxGraphRepository()
    repo.add_nodes([
        Node(id="Ni_recovery", label="Извлечение Ni", type="KPI"),
        Node(id="CMC", label="CMC", type="reagent"),  # не связан с KPI → пробел
    ])
    return repo


def test_scout_makes_steps_and_mines_triplet():
    repo = _kpi_graph()
    doc = Document(id="openalex_NEW", title="CMC improves nickel recovery", year=2022,
                   source="openalex", text="cmc improves nickel recovery in flotation")
    agent = LangGraphResearchAgent(
        graph_repository=repo, extractor=StubExtractor(), source=FakeSource([doc]),
        use_llm=False, max_steps=3,
    )
    res = agent.run("scout", {"kpi": "извлечение Ni +2%"})
    assert res.mission == "scout"
    assert len(res.triplets) >= 1                      # добыт ≥1 новый цитированный факт
    assert res.triplets[0].evidence_quote              # с цитатой
    tools = {s.tool for s in res.trace.steps}
    assert {"plan", "search_literature", "observe", "reflect"} <= tools  # осмысленные шаги
    assert res.trace.mission == "scout" and res.sources == ["openalex_NEW"]


def test_budget_caps_the_loop():
    repo = NetworkxGraphRepository()
    repo.add_nodes(
        [Node(id="Ni_recovery", label="KPI", type="KPI")]
        + [Node(id=f"r{i}", label=f"reagent{i}", type="reagent") for i in range(6)]  # 6 пробелов
    )
    agent = LangGraphResearchAgent(
        graph_repository=repo, extractor=StubExtractor(), source=CountingSource(),
        use_llm=False, max_steps=2, max_stagnation=5,  # стоп должен прийти по max_steps
    )
    res = agent.run("scout", {"kpi": "извлечение Ni"})
    searches = [s for s in res.trace.steps if s.tool == "search_literature"]
    assert len(searches) == 2                # бюджет реально оборвал петлю на 2 шагах из 6
    assert any("стоп" in s.thought for s in res.trace.steps if s.tool == "reflect")


def test_stagnation_stops_when_no_new_facts():
    repo = _kpi_graph()
    repo.add_nodes([Node(id=f"r{i}", label=f"r{i}", type="reagent") for i in range(5)])
    doc = Document(id="openalex_DUP", title="dup", year=2020, source="openalex", text="t")
    agent = LangGraphResearchAgent(
        graph_repository=repo, extractor=StubExtractor(), source=FakeSource([doc]),
        use_llm=False, max_steps=9, max_stagnation=2,  # один и тот же doc → дубли → стагнация
    )
    res = agent.run("scout", {"kpi": "извлечение Ni"})
    # первый шаг добывает факт, дальше дубликаты → стоп по стагнации задолго до max_steps
    searches = [s for s in res.trace.steps if s.tool == "search_literature"]
    assert len(searches) <= 4


def test_enrich_graph_refreezes_snapshot():
    repo = NetworkxGraphRepository()
    repo.add_nodes([Node(id="pH", label="pH", type="parameter"),
                    Node(id="Ni_recovery", label="Извлечение Ni", type="KPI")])
    repo.add_edges([Edge(source="pH", target="Ni_recovery", sign="+", doc_id="d0",
                         evidence_quote="q0", year=2009)])
    before = graph_snapshot_id(repo)

    class FixedAgent:
        def run(self, mission, input):
            t = Triplet(id="n", chunk_id="c", doc_id="newdoc", subject="CMC",
                        relation="повышает", object="извлечение Ni", sign="+",
                        evidence_quote="cmc", year=2022)
            return AgentResult(mission="scout", triplets=[t],
                               trace=AgentTrace(id="tr1", mission="scout", steps=[]))

    from app.infrastructure.embeddings import EntityNormalizer

    eg = EnrichGraph(FixedAgent(), repo, EntityNormalizer())
    snap = eg.execute("извлечение Ni")
    assert snap.snapshot_id != before          # новые факты → новый snapshot_id
    assert eg.last_trace.id == "tr1"
    assert any(e.source == "CMC" for e in repo.all_edges())  # факт реально в графе
