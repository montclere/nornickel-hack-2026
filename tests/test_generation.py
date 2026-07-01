"""Юнит-тесты генераторов гипотез на рукотворных графах.

Каждый генератор проверяется на маленьком графе с известным ожиданием; оркестратор
— на канонической фикстуре. Детерминизм: повторный прогон идентичен.
"""

from __future__ import annotations

from app.infrastructure.fakes import FakeGraphRepository
from app.service.domain.generation import (
    anti_rake,
    contradictions,
    gaps,
    generate_candidates,
    reanimation,
)
from app.service.entities import Edge, Node
from tests.conftest import load_fixture


def _repo(nodes: list[Node], edges: list[Edge]) -> FakeGraphRepository:
    repo = FakeGraphRepository()
    repo.add_nodes(nodes)
    repo.add_edges(edges)
    return repo


def _edge(source: str, target: str, sign: str = "+", year: int = 2010, doc: str = "d",
          conditions: dict | None = None) -> Edge:
    return Edge(
        source=source, target=target, sign=sign, conditions=conditions or {},
        doc_id=doc, evidence_quote="q", year=year,
    )


# --- gaps (ABC Свонсона) -----------------------------------------------------


def test_gaps_finds_abc_chain():
    repo = _repo(
        [
            Node(id="R", label="Реагент R", type="reagent"),
            Node(id="P", label="Параметр P", type="parameter"),
            Node(id="K", label="KPI K", type="KPI"),
        ],
        [_edge("R", "P", year=2015), _edge("P", "K", year=2016)],
    )
    out = gaps.generate(repo, "K")
    assert len(out) == 1
    h = out[0]
    assert h.origin == "gap"
    assert h.id == "h_gap__R__K"
    assert [(e.source, e.target) for e in h.evidence_path] == [("R", "P"), ("P", "K")]


def test_gaps_skips_when_direct_edge_exists():
    repo = _repo(
        [
            Node(id="R", label="R", type="reagent"),
            Node(id="P", label="P", type="parameter"),
            Node(id="K", label="K", type="KPI"),
        ],
        [_edge("R", "P"), _edge("P", "K"), _edge("R", "K", year=2012)],  # прямая R→K
    )
    assert gaps.generate(repo, "K") == []


def test_gaps_respects_types():
    # A — material (не reagent) → не разрыв
    repo = _repo(
        [
            Node(id="M", label="M", type="material"),
            Node(id="P", label="P", type="parameter"),
            Node(id="K", label="K", type="KPI"),
        ],
        [_edge("M", "P"), _edge("P", "K")],
    )
    assert gaps.generate(repo, "K") == []


def test_gaps_resolves_only_kpi_target():
    repo = _repo([Node(id="K", label="K", type="parameter")], [])
    assert gaps.generate(repo, "K") == []  # цель не KPI
    assert gaps.generate(repo, None) == []


# --- reanimation -------------------------------------------------------------


def _reanim_repo(fresh_quote: str, fresh_year: int = 2021) -> FakeGraphRepository:
    return _repo(
        [
            Node(id="X", label="Реагент X", type="reagent"),
            Node(id="cost", label="Стоимость", type="parameter"),
            Node(id="F", label="Отказ X (2012)", type="failure", closure_reason="дорого"),
        ],
        [
            _edge("X", "F", sign="0", year=2012, doc="report_2012"),
            Edge(source="X", target="cost", sign="-", conditions={},
                 doc_id="openalex_2021", evidence_quote=fresh_quote, year=fresh_year),
        ],
    )


def test_reanimation_lifts_cost_reason():
    repo = _reanim_repo("A low-cost synthesis route reduces reagent cost by 60%.")
    out = reanimation.generate(repo, "K")
    assert len(out) == 1
    h = out[0]
    assert h.origin == "reanimation" and h.id == "h_reanim__F"
    assert sorted(h.sources) == ["openalex_2021", "report_2012"]


def test_reanimation_requires_fresh_fact():
    # цитата не снимает причину «дорого»
    repo = _reanim_repo("collector improves selectivity")
    assert reanimation.generate(repo, "K") == []


def test_reanimation_requires_newer_year():
    # свежий факт старше года провала → не реанимируем
    repo = _reanim_repo("low-cost synthesis reduces cost", fresh_year=2010)
    assert reanimation.generate(repo, "K") == []


# --- contradictions ----------------------------------------------------------


def test_contradiction_opposite_signs_different_years():
    repo = _repo(
        [Node(id="A", label="A", type="parameter"), Node(id="B", label="B", type="KPI")],
        [
            _edge("A", "B", sign="+", year=2009, conditions={"ore": "pentlandite"}),
            _edge("A", "B", sign="-", year=2019, conditions={"ore": "pyrrhotite"}),
        ],
    )
    out = contradictions.generate(repo)
    assert len(out) == 1
    h = out[0]
    assert h.origin == "contradiction" and h.id == "h_contra__A__B"
    assert "«ore»" in h.statement_if  # различающееся условие извлечено


def test_contradiction_same_year_ignored():
    repo = _repo(
        [Node(id="A", label="A", type="parameter"), Node(id="B", label="B", type="KPI")],
        [_edge("A", "B", sign="+", year=2009), _edge("A", "B", sign="-", year=2009)],
    )
    assert contradictions.generate(repo) == []


# --- anti_rake ---------------------------------------------------------------


def test_anti_rake_flags_overlap_with_graveyard():
    repo = _repo(
        [
            Node(id="X", label="X", type="reagent"),
            Node(id="F", label="Отказ X", type="failure", closure_reason="дорого"),
        ],
        [_edge("X", "F", sign="0", year=2012, doc="report_2012")],
    )
    from app.service.entities import ExperimentProtocol, Hypothesis

    hyp = Hypothesis(
        id="h_x", statement_if="...", statement_then="...", statement_because="...",
        origin="gap",
        evidence_path=[_edge("X", "F", sign="0", year=2012, doc="report_2012")],
        experiment_protocol=ExperimentProtocol(method="m", equipment="e",
                                               duration_days=1, cost_rub=1),
    )
    checked = anti_rake.apply(repo, [hyp])
    gc = checked[0].graveyard_check
    assert gc.warning is True
    assert gc.report_ref == "report_2012" and gc.reason == "дорого"
    assert gc.difference  # «чем отличается» заполнено


def test_anti_rake_no_warning_when_disjoint():
    repo = _repo(
        [Node(id="F", label="F", type="failure", closure_reason="дорого")],
        [],
    )
    from app.service.entities import ExperimentProtocol, Hypothesis

    hyp = Hypothesis(
        id="h", statement_if="i", statement_then="t", statement_because="b",
        origin="gap", evidence_path=[_edge("A", "B")],
        experiment_protocol=ExperimentProtocol(method="m", equipment="e",
                                               duration_days=1, cost_rub=1),
    )
    assert anti_rake.apply(repo, [hyp])[0].graveyard_check.warning is False


# --- orchestrator on the canonical fixture graph -----------------------------


def _fixture_repo() -> FakeGraphRepository:
    return _repo(
        [Node(**n) for n in load_fixture("nodes.json")],
        [Edge(**e) for e in load_fixture("edges.json")],
    )


def test_orchestrator_yields_all_origins_with_graveyard_check():
    repo = _fixture_repo()
    out = generate_candidates(repo, "извлечение Ni +2%")
    assert out, "оркестратор должен выдать непустой список на фикстурном графе"

    origins = {h.origin for h in out}
    assert origins == {"gap", "reanimation", "contradiction"}

    # у каждой гипотезы есть graveyard_check; есть origin
    assert all(h.graveyard_check is not None and h.origin for h in out)

    # реанимация коллектора X помечена анти-граблями (пересекается с кладбищем)
    reanim = next(h for h in out if h.origin == "reanimation")
    assert reanim.graveyard_check.warning is True
    assert reanim.graveyard_check.report_ref == "report_2012"

    # детерминированный порядок: gap → reanimation → contradiction
    assert [h.origin for h in out] == ["gap", "reanimation", "contradiction"]


def test_orchestrator_is_deterministic():
    a = generate_candidates(_fixture_repo(), "извлечение Ni +2%")
    b = generate_candidates(_fixture_repo(), "извлечение Ni +2%")
    assert [h.model_dump() for h in a] == [h.model_dump() for h in b]
