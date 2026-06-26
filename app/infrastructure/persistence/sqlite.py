"""Реализации персиста на стандартном sqlite3.

CorpusRepository (документы/триплеты), FeedbackRepository (решения эксперта),
RankerStateStore (веса ранкера). Хранение — JSON сущностей в текстовых колонках:
просто, переносимо, без ORM. Одно соединение шарится между репозиториями (важно для
режима ":memory:", где БД живёт ровно в рамках соединения)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.service.domain.scoring import default_weights
from app.service.entities import Document, Feedback, Triplet


def connect(db_path: str | Path = ":memory:") -> sqlite3.Connection:
    """Открыть соединение (check_same_thread=False — FastAPI ходит из разных потоков)."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


class SQLiteCorpusRepository:
    """Документы корпуса и извлечённые триплеты."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        conn.execute("CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, data TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS triplets (id TEXT PRIMARY KEY, data TEXT)")
        conn.commit()

    def save_documents(self, documents: list[Document]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO documents (id, data) VALUES (?, ?)",
            [(d.id, d.model_dump_json()) for d in documents],
        )
        self.conn.commit()

    def load_documents(self) -> list[Document]:
        rows = self.conn.execute("SELECT data FROM documents ORDER BY id").fetchall()
        return [Document.model_validate_json(r[0]) for r in rows]

    def save_triplets(self, triplets: list[Triplet]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO triplets (id, data) VALUES (?, ?)",
            [(t.id, t.model_dump_json()) for t in triplets],
        )
        self.conn.commit()

    def load_triplets(self) -> list[Triplet]:
        rows = self.conn.execute("SELECT data FROM triplets ORDER BY id").fetchall()
        return [Triplet.model_validate_json(r[0]) for r in rows]


class SQLiteFeedbackRepository:
    """Журнал решений эксперта (accept/reject/edit)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        conn.execute(
            "CREATE TABLE IF NOT EXISTS feedback "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT)"
        )
        conn.commit()

    def add(self, feedback: Feedback) -> None:
        self.conn.execute(
            "INSERT INTO feedback (data) VALUES (?)", (feedback.model_dump_json(),)
        )
        self.conn.commit()

    def all(self) -> list[Feedback]:
        rows = self.conn.execute("SELECT data FROM feedback ORDER BY id").fetchall()
        return [Feedback.model_validate_json(r[0]) for r in rows]


class SQLiteRankerStateStore:
    """Веса интерпретируемого ранкера (одна строка)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ranker_weights "
            "(id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT)"
        )
        conn.commit()

    def load_weights(self) -> dict[str, float]:
        row = self.conn.execute(
            "SELECT data FROM ranker_weights WHERE id = 1"
        ).fetchone()
        if row is None:
            return default_weights()
        import json

        return {k: float(v) for k, v in json.loads(row[0]).items()}

    def save_weights(self, weights: dict[str, float]) -> None:
        import json

        self.conn.execute(
            "INSERT OR REPLACE INTO ranker_weights (id, data) VALUES (1, ?)",
            (json.dumps(weights),),
        )
        self.conn.commit()


__all__ = [
    "connect",
    "SQLiteCorpusRepository",
    "SQLiteFeedbackRepository",
    "SQLiteRankerStateStore",
]
