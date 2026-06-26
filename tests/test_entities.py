"""Каждая сущность имеет валидный пример-фикстуру и round-trip через pydantic."""

from __future__ import annotations

import pytest

from app.service.entities import (
    AgentResult,
    AgentTrace,
    Chunk,
    Document,
    Edge,
    Feedback,
    GraphSnapshot,
    Hypothesis,
    Node,
    ParsedDocument,
    Triplet,
)
from tests.conftest import load_fixture

# одиночная фикстура → её модель
SINGLE_FIXTURES = {
    "document.json": Document,
    "parsed_document.json": ParsedDocument,
    "chunk.json": Chunk,
    "triplet.json": Triplet,
    "node.json": Node,
    "edge.json": Edge,
    "hypothesis.json": Hypothesis,
    "feedback.json": Feedback,
    "agent_trace.json": AgentTrace,
    "graph_snapshot.json": GraphSnapshot,
    "agent_result_scout.json": AgentResult,
    "agent_result_chat.json": AgentResult,
}

# коллекция-фикстура → модель элемента
LIST_FIXTURES = {
    "documents.json": Document,
    "triplets.json": Triplet,
    "nodes.json": Node,
    "edges.json": Edge,
}


@pytest.mark.parametrize("filename,model", SINGLE_FIXTURES.items())
def test_single_fixture_validates(filename, model):
    data = load_fixture(filename)
    obj = model(**data)
    # round-trip: модель сериализуется обратно без потерь типов
    assert model(**obj.model_dump()) == obj


@pytest.mark.parametrize("filename,model", LIST_FIXTURES.items())
def test_list_fixture_validates(filename, model):
    items = load_fixture(filename)
    assert isinstance(items, list) and items
    for item in items:
        model(**item)


def test_phrased_card_alias():
    from app.service.entities import PhrasedCard

    card = PhrasedCard(**{"if": "A", "then": "B", "because": "C"})
    assert card.if_ == "A"
    # сериализация по алиасу даёт ключ "if"
    assert card.model_dump(by_alias=True)["if"] == "A"


def test_sign_literal_rejects_garbage():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Edge(
            source="a",
            target="b",
            sign="??",  # не входит в Literal["+","-","0"]
            doc_id="d",
            evidence_quote="q",
            year=2020,
        )
