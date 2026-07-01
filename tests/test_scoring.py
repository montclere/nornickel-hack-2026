"""Тесты скоринга и интерпретируемого ранкера.

Метрики воспроизводимы на фиксированном графе; ранкер сортирует и объясняет ранг;
имитация 10 фидбеков заметно сдвигает веса.
"""

from __future__ import annotations

import pytest

from app.infrastructure.fakes import FakeGraphRepository
from app.service.domain.generation import generate_candidates
from app.service.domain.scoring import feedback, metrics, ranker
from app.service.entities import Edge, ExperimentProtocol, Hypothesis, Node
from tests.conftest import load_fixture


def _edge(source: str, target: str, sign: str = "+", year: int = 2010, doc: str = "d") -> Edge:
    return Edge(source=source, target=target, sign=sign, conditions={},
               doc_id=doc, evidence_quote="q", year=year)


def _hyp(evidence: list[Edge], cost: int = 600_000, warning: bool = False) -> Hypothesis:
    from app.service.entities import GraveyardCheck

    return Hypothesis(
        id="h", statement_if="i", statement_then="t", statement_because="b",
        origin="gap", evidence_path=evidence,
        graveyard_check=GraveyardCheck(warning=warning),
        experiment_protocol=ExperimentProtocol(method="m", equipment="e",
                                               duration_days=10, cost_rub=cost),
    )


# --- metrics: воспроизводимость на фиксированном графе ------------------------


def _ab_repo() -> FakeGraphRepository:
    repo = FakeGraphRepository()
    repo.add_nodes([Node(id="A", label="A", type="reagent"),
                    Node(id="B", label="B", type="parameter")])
    repo.add_edges([_edge("A", "B")])
    return repo


def test_metrics_known_values():
    repo = _ab_repo()
    m = metrics.compute(_hyp([_edge("A", "B")], cost=600_000), repo, kpi_id=None)
    # novelty: avg_deg=1 → 1 - 1/6
    assert m.novelty.value == pytest.approx(1 - 1 / 6, abs=1e-9)
    # risk: trl mean(5,7)=6 → trl_risk=1-6/9; нет конфликтов, нет кладбища
    assert m.risk.value == pytest.approx(0.5 * (1 - 6 / 9), abs=1e-9)
    # value: kpi=None → sensitivity 0.5; cost_norm=0.2 → cost_adj 0.8
    assert m.value.value == pytest.approx(0.6 * 0.5 + 0.4 * 0.8, abs=1e-9)
    # признаки
    assert m.features["chain_len"] == pytest.approx(0.25)
    assert m.features["conflict"] == pytest.approx(0.0)
    assert m.features["cost"] == pytest.approx(0.2)


def test_metrics_breakdown_present_for_ui():
    m = metrics.compute(_hyp([_edge("A", "B")]), _ab_repo())
    assert "path_rarity" in m.novelty.components
    assert {"trl_risk", "source_conflict", "graveyard"} <= set(m.risk.components)
    assert {"kpi_sensitivity", "cost_adjustment"} <= set(m.value.components)


def test_metrics_deterministic():
    repo = _ab_repo()
    a = metrics.compute(_hyp([_edge("A", "B")]), repo)
    b = metrics.compute(_hyp([_edge("A", "B")]), repo)
    assert a.features == b.features and a.novelty.value == b.novelty.value


def test_novelty_uses_embedding_distance_when_given():
    repo = _ab_repo()
    near = metrics.novelty(_hyp([_edge("A", "B")]), repo, embedding_distance=0.0)
    far = metrics.novelty(_hyp([_edge("A", "B")]), repo, embedding_distance=1.0)
    assert far.value > near.value  # дальше от существующих работ → новее


def test_higher_graveyard_and_cost_raise_risk_and_drop_value():
    repo = _ab_repo()
    base = metrics.compute(_hyp([_edge("A", "B")], cost=300_000, warning=False), repo)
    risky = metrics.compute(_hyp([_edge("A", "B")], cost=3_000_000, warning=True), repo)
    assert risky.risk.value > base.risk.value
    assert risky.value.value < base.value.value


# --- ranker: сортирует и объясняет -------------------------------------------


def _fixture_repo() -> FakeGraphRepository:
    repo = FakeGraphRepository()
    repo.add_nodes([Node(**n) for n in load_fixture("nodes.json")])
    repo.add_edges([Edge(**e) for e in load_fixture("edges.json")])
    return repo


def test_ranker_sorts_and_explains():
    repo = _fixture_repo()
    candidates = generate_candidates(repo, "извлечение Ni +2%")
    ranked = ranker.rank(candidates, repo, "извлечение Ni +2%")

    # отсортировано по убыванию rank_score
    scores = [h.rank_score for h in ranked]
    assert scores == sorted(scores, reverse=True)
    # каждая карточка объяснима: метрики в [0,1], вклад признаков = rank_score
    for h in ranked:
        assert h.rank_score is not None
        assert 0.0 <= h.novelty <= 1.0 and 0.0 <= h.risk <= 1.0 and 0.0 <= h.value <= 1.0
        assert h.novelty_breakdown and h.rank_contributions
        assert sum(h.rank_contributions.values()) == pytest.approx(h.rank_score, abs=1e-9)
        assert set(h.rank_contributions) == set(ranker.FEATURES)


def test_ranker_deterministic():
    repo = _fixture_repo()
    cands = generate_candidates(repo, "извлечение Ni +2%")
    a = ranker.rank(cands, repo, "извлечение Ni +2%")
    b = ranker.rank(cands, repo, "извлечение Ni +2%")
    assert [h.model_dump() for h in a] == [h.model_dump() for h in b]


def test_weights_editable_change_order_possible():
    repo = _fixture_repo()
    cands = generate_candidates(repo, "извлечение Ni +2%")
    # инвертируем знак риска в весах → ранги пересчитываются
    w = ranker.default_weights()
    w["risk"] = +5.0
    ranked = ranker.rank(cands, repo, "извлечение Ni +2%", weights=w)
    assert all(h.rank_contributions["risk"] >= 0 for h in ranked)


# --- feedback: дообучение сдвигает веса --------------------------------------


def _feature(novelty: float, risk: float) -> dict[str, float]:
    # остальные признаки держим постоянными, чтобы их вес остался ~0
    return {"novelty": novelty, "risk": risk, "value": 0.5,
            "chain_len": 0.5, "conflict": 0.5, "cost": 0.5}


def test_feedback_shifts_weights():
    pytest.importorskip("sklearn")
    # accept: низкий риск; reject: высокий риск (риск идеально разделяет классы),
    # новизна слегка перекрывается между классами (плохо разделяет)
    accepts = [(_feature(0.6 + 0.02 * i, 0.1), 1) for i in range(5)]
    rejects = [(_feature(0.5 + 0.02 * i, 0.9), 0) for i in range(5)]
    samples = accepts + rejects  # 10 примеров

    before = ranker.default_weights()
    after = feedback.retrain(samples, before)

    assert after != before  # веса заметно сдвинулись
    assert after["risk"] < 0  # выше риск → чаще отклоняют
    # риск стал весить больше новизны (как в примере из ТЗ)
    assert abs(after["risk"]) > abs(after["novelty"])


def test_feedback_needs_both_classes():
    pytest.importorskip("sklearn")
    only_accepts = [(_feature(0.6, 0.1), 1) for _ in range(10)]
    before = ranker.default_weights()
    assert feedback.retrain(only_accepts, before) == before  # учиться нечему


def test_build_samples_joins_feedback_with_hypotheses():
    repo = _fixture_repo()
    cands = ranker.rank(generate_candidates(repo, "извлечение Ni +2%"), repo, "извлечение Ni +2%")
    from app.service.entities import Feedback

    fbs = [
        Feedback(hypothesis_id=cands[0].id, decision="accept", reason="ok"),
        Feedback(hypothesis_id=cands[-1].id, decision="reject", reason="дорого"),
        Feedback(hypothesis_id="missing", decision="accept", reason="—"),  # игнор
    ]
    samples = feedback.build_samples(fbs, cands, repo, "извлечение Ni +2%")
    assert len(samples) == 2
    assert {label for _, label in samples} == {0, 1}
    assert all(set(feat) == set(ranker.FEATURES) for feat, _ in samples)
