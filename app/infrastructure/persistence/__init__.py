"""Персист на SQLite: корпус, фидбек, веса ранкера.

Конкретные классы, инжектятся в use-cases/API через конструктор (отдельный Protocol
им не нужен — в тестах подменяются через db_path=":memory:" или tmp-файл).
"""

from app.infrastructure.persistence.sqlite import (
    SQLiteCorpusRepository,
    SQLiteFeedbackRepository,
    SQLiteRankerStateStore,
    connect,
)

__all__ = [
    "connect",
    "SQLiteCorpusRepository",
    "SQLiteFeedbackRepository",
    "SQLiteRankerStateStore",
]
