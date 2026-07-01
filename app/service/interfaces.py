"""Protocol-интерфейсы ТОЛЬКО подменяемых зависимостей.

Эти порты реализуются в `app.infrastructure` (real + fake) и инжектятся в
use-cases (`app.service.pipeline`) через конструктор. `domain` зависит лишь от
`GraphRepository` (и то — как от данных).

Остальное (OpenAlex-источник, эмбеддинги, SQLite-персист) — конкретные классы в
infrastructure, передаются в pipeline без отдельного интерфейса (в тестах при
необходимости подменяются fake-версией).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from app.service.entities import (
    AgentResult,
    Chunk,
    Edge,
    Mission,
    Node,
    ParsedDocument,
    PhrasedCard,
    Triplet,
)


@runtime_checkable
class Ocr(Protocol):
    """Разбор скана/PDF без текстового слоя в markdown."""

    def parse(self, file_path: Path) -> ParsedDocument: ...


@runtime_checkable
class FactExtractor(Protocol):
    """Извлечение триплетов из фрагмента (LLM + цитатный гейт)."""

    def extract(self, chunk: Chunk) -> list[Triplet]: ...


@runtime_checkable
class CardPhrasing(Protocol):
    """Оформление структурированных полей в текст «ЕСЛИ-ТО-ПОТОМУ ЧТО».

    LLM ничего не выдумывает — только переформулирует переданные поля.
    """

    def phrase(self, pattern_fields: dict) -> PhrasedCard: ...


@runtime_checkable
class GraphRepository(Protocol):
    """Хранилище графа знаний (NetworkX/Neo4j). Единственная дверь
    домена к графу — поэтому ядро остаётся независимым от реализации."""

    def add_nodes(self, nodes: list[Node]) -> None: ...

    def add_edges(self, edges: list[Edge]) -> None: ...

    def query_paths(
        self, source: str, target: str, max_len: int = 3
    ) -> list[list[Edge]]: ...

    def neighbors(self, node_id: str) -> list[Node]: ...

    def conflicting_edges(self) -> list[tuple[Edge, Edge]]: ...

    def failure_nodes(self) -> list[Node]: ...

    # --- чтение для чистого ядра (домен ходит в граф ТОЛЬКО через эти методы) ---
    def get_node(self, node_id: str) -> Node | None: ...

    def all_nodes(self) -> list[Node]: ...

    def all_edges(self) -> list[Edge]: ...

    def out_edges(self, node_id: str) -> list[Edge]: ...

    def in_edges(self, node_id: str) -> list[Edge]: ...

    def save(self, path: Path) -> None: ...

    def load(self, path: Path) -> None: ...


@runtime_checkable
class ResearchAgent(Protocol):
    """Агентный рантайм (LangGraph). Один движок, два режима.

    mission="scout" → дозаполняет граф цитированными триплетами (+ трейл);
    mission="chat"  → отвечает по графу со ссылками, read-only (+ трейл).
    """

    def run(self, mission: Mission, input: dict) -> AgentResult: ...


__all__ = ["Ocr", "FactExtractor", "CardPhrasing", "GraphRepository", "ResearchAgent"]
