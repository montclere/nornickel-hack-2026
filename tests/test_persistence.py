"""Тесты SQLite-персиста."""

from __future__ import annotations

from app.infrastructure.persistence import (
    SQLiteCorpusRepository,
    SQLiteFeedbackRepository,
    SQLiteRankerStateStore,
    connect,
)
from app.service.domain.scoring import default_weights
from app.service.entities import Document, Feedback, Triplet
from tests.conftest import load_fixture


def test_corpus_roundtrip(tmp_path):
    conn = connect(tmp_path / "phoenix.db")
    repo = SQLiteCorpusRepository(conn)
    docs = [Document(**d) for d in load_fixture("documents.json")]
    triplets = [Triplet(**t) for t in load_fixture("triplets.json")]
    repo.save_documents(docs)
    repo.save_triplets(triplets)
    # повторная запись идемпотентна (INSERT OR REPLACE по id)
    repo.save_documents(docs)
    assert {d.id for d in repo.load_documents()} == {d.id for d in docs}
    assert {t.id for t in repo.load_triplets()} == {t.id for t in triplets}


def test_feedback_repository_appends():
    repo = SQLiteFeedbackRepository(connect(":memory:"))
    repo.add(Feedback(**load_fixture("feedback.json")))
    repo.add(Feedback(hypothesis_id="x", decision="accept", reason="ok"))
    rows = repo.all()
    assert len(rows) == 2 and {r.decision for r in rows} == {"reject", "accept"}


def test_ranker_state_store_defaults_then_persists(tmp_path):
    store = SQLiteRankerStateStore(connect(tmp_path / "w.db"))
    assert store.load_weights() == default_weights()  # пусто → дефолт
    store.save_weights({"novelty": 9.0, "risk": -9.0})
    assert store.load_weights() == {"novelty": 9.0, "risk": -9.0}


def test_memory_db_shared_connection():
    # три репозитория на одном :memory:-соединении видят общую БД
    conn = connect(":memory:")
    SQLiteCorpusRepository(conn)
    fb = SQLiteFeedbackRepository(conn)
    SQLiteRankerStateStore(conn).save_weights({"novelty": 1.0})
    fb.add(Feedback(hypothesis_id="h", decision="reject", reason="r"))
    assert len(fb.all()) == 1
