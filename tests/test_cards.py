"""Тесты сборки карточки + постпроверки «никаких новых сущностей»."""

from __future__ import annotations

from app.container import build
from app.infrastructure.fakes import FakeCardPhrasing, FakeGraphRepository
from app.service.domain import cards
from app.service.entities import (
    Edge,
    ExperimentProtocol,
    Hypothesis,
    Node,
    PhrasedCard,
)
from tests.conftest import load_fixture

KPI = "извлечение Ni +2%"


def _fixture_repo() -> FakeGraphRepository:
    repo = FakeGraphRepository()
    repo.add_nodes([Node(**n) for n in load_fixture("nodes.json")])
    repo.add_edges([Edge(**e) for e in load_fixture("edges.json")])
    return repo


def _hyp_on(edges: list[Edge], because: str = "механизм") -> Hypothesis:
    return Hypothesis(
        id="h", statement_if="i", statement_then="t", statement_because=because,
        origin="gap", evidence_path=edges,
        experiment_protocol=ExperimentProtocol(method="m", equipment="e",
                                               duration_days=10, cost_rub=1),
    )


# --- pattern_fields -----------------------------------------------------------


def test_pattern_fields_grounded_in_graph():
    repo = _fixture_repo()
    edge = Edge(**load_fixture("edge.json"))  # pH → Ni_recovery
    fields = cards.pattern_fields(_hyp_on([edge]), repo, KPI)
    assert fields["intervention"] == "pH пульпы"
    assert fields["effect_target"] == "Извлечение Ni"  # KPI разрешён даже вне evidence
    assert "baseline" in fields and fields["evidence"]
    # evidence кликается до первоисточника
    assert fields["evidence"][0]["quote"] and fields["evidence"][0]["doc_id"]


# --- постпроверка «никаких новых сущностей» -----------------------------------


def test_verify_catches_new_entity():
    repo = _fixture_repo()
    repo.add_nodes([Node(id="Cu", label="Медь", type="material", aliases=["copper"])])
    edge = Edge(**load_fixture("edge.json"))  # pH → Ni_recovery (без Cu)
    hyp = _hyp_on([edge])
    bad = PhrasedCard(**{"if": "поднять pH", "then": "вырастет извлечение Ni",
                         "because": "это также активирует Медь в пульпе"})
    offenders = cards.verify_no_new_entities(
        " ".join([bad.if_, bad.then, bad.because]), hyp, repo, KPI
    )
    assert "Медь" in offenders  # «Медь» нет в evidence_path → поймано


def test_assemble_rejects_violation_keeps_baseline():
    repo = _fixture_repo()
    repo.add_nodes([Node(id="Cu", label="Медь", type="material", aliases=["copper"])])
    edge = Edge(**load_fixture("edge.json"))
    hyp = _hyp_on([edge], because="базовый механизм")
    bad = PhrasedCard(**{"if": "поднять pH", "then": "вырастет извлечение Ni",
                         "because": "за счёт активации Медь"})
    result = cards.assemble(hyp, bad, repo, KPI)
    # текст-галлюцинация наружу не ушёл: остался baseline + флаг
    assert result.statement_because == "базовый механизм"
    assert result.phrasing_flag and "Медь" in result.phrasing_flag


def test_assemble_accepts_clean_phrasing():
    repo = _fixture_repo()
    edge = Edge(**load_fixture("edge.json"))
    hyp = _hyp_on([edge])
    clean = PhrasedCard(**{"if": "повысить «pH пульпы»",
                           "then": "вырастет «Извлечение Ni»",
                           "because": "pH пульпы влияет на извлечение Ni"})
    result = cards.assemble(hyp, clean, repo, KPI)
    assert result.phrasing_flag is None
    assert result.statement_if == "повысить «pH пульпы»"


def test_kpi_mention_not_flagged_for_reanimation():
    # реанимация не содержит KPI в evidence_path, но упоминать его в тексте можно
    repo = _fixture_repo()
    link = Edge(source="collector_X", target="failure_collector_X_2012", sign="0",
                doc_id="report_2012", evidence_quote="q", year=2012)
    fresh = Edge(source="collector_X", target="стоимость_синтеза", sign="-",
                 doc_id="openalex_2021", evidence_quote="q", year=2021)
    hyp = Hypothesis(
        id="r", statement_if="i", statement_then="t", statement_because="b",
        origin="reanimation", evidence_path=[link, fresh],
        experiment_protocol=ExperimentProtocol(method="m", equipment="e",
                                               duration_days=10, cost_rub=1),
    )
    card = PhrasedCard(**{"if": "вернуть «Коллектор X»",
                          "then": "вырастет «Извлечение Ni»",
                          "because": "удешевление снимает причину отказа"})
    assert cards.assemble(hyp, card, repo, KPI).phrasing_flag is None


# --- FakeCardPhrasing + сквозной поток ----------------------------------------


def test_fake_phrasing_echoes_baseline():
    fields = {"baseline": {"if": "A", "then": "B", "because": "C"},
              "intervention": "X", "effect_target": "Y", "mechanism": "Z"}
    card = FakeCardPhrasing().phrase(fields)
    assert (card.if_, card.then, card.because) == ("A", "B", "C")


def test_generate_produces_valid_if_then_because_no_hallucination():
    c = build("fake")
    c.graph_repository.add_nodes([Node(**n) for n in load_fixture("nodes.json")])
    c.graph_repository.add_edges([Edge(**e) for e in load_fixture("edges.json")])
    hyps = c.generate_hypotheses.execute(KPI)
    assert hyps
    for h in hyps:
        # формат ЕСЛИ-ТО-ПОТОМУ ЧТО заполнен
        assert h.statement_if and h.statement_then and h.statement_because
        # на фейке текст заземлён → постпроверка не сработала
        assert h.phrasing_flag is None
        # карточка кликается до первоисточников
        assert h.sources and all(e.evidence_quote and e.doc_id for e in h.evidence_path)
