"""Детерминированные fake-реализации портов — оффлайн-бэкбон проекта.

Все данные берутся из `fixtures/`, поэтому весь pipeline собирается и прогоняется
end-to-end без сети, ключей API и GPU. Реальные адаптеры
подменяют эти fake-классы в `app.container` независимо друг от друга.

Состав:
    FakeOcr            sidecar .txt рядом со сканом → markdown (иначе — канон из фикстур)
    FakeFactExtractor  триплеты из fixtures/triplets.json по doc_id фрагмента
    FakeCardPhrasing   шаблонная сборка текста {if, then, because} без API
    FakeGraphRepository in-memory граф (чистый Python) с рабочими запросами
    FakeResearchAgent  scout → триплеты+трейл, chat → ответ+ссылки+трейл (из фикстур)
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.config import FIXTURES_DIR
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


# --- загрузка фикстур ---------------------------------------------------------


@lru_cache(maxsize=None)
def _load_fixture(name: str) -> object:
    """Прочитать и закешировать fixtures/<name> (JSON)."""
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


# --- порты --------------------------------------------------------------------


class FakeOcr:
    """OCR-заглушка: читает sidecar `<скан>.txt`; если его нет — канон из фикстуры.

    Активна, когда GPU недоступен (или PHOENIX_OCR=fake) — остальная команда не
    блокируется отсутствием видеокарты.
    """

    def parse(self, file_path: Path) -> ParsedDocument:
        file_path = Path(file_path)
        sidecar = file_path.with_suffix(file_path.suffix + ".txt")
        if sidecar.exists():
            markdown = sidecar.read_text(encoding="utf-8")
            meta = {"source": "sidecar", "path": str(sidecar)}
        else:
            data = _load_fixture("parsed_document.json")
            assert isinstance(data, dict)
            markdown = str(data["markdown"])
            meta = {"source": "fixture", "path": str(file_path)}
        return ParsedDocument(
            doc_id=file_path.stem,
            markdown=markdown,
            pages=[markdown],
            meta=meta,
        )


class FakeFactExtractor:
    """Возвращает из fixtures/triplets.json триплеты с doc_id фрагмента.

    Цитата каждого триплета сохранена дословно — формат совпадает с реальным
    экстрактором, чтобы цитатный гейт работал одинаково.
    """

    def __init__(self) -> None:
        raw = _load_fixture("triplets.json")
        assert isinstance(raw, list)
        self._by_doc: dict[str, list[dict]] = {}
        for item in raw:
            self._by_doc.setdefault(item["doc_id"], []).append(item)

    def extract(self, chunk: Chunk) -> list[Triplet]:
        out: list[Triplet] = []
        for i, item in enumerate(self._by_doc.get(chunk.doc_id, [])):
            data = dict(item)
            data["chunk_id"] = chunk.id  # привязать к реальному фрагменту
            out.append(Triplet(**data))
        return out


class FakeCardPhrasing:
    """Шаблонная сборка текста карточки без LLM (детерминированно, заземлено).

    Если в полях есть детерминированный baseline генератора — отдаём его (он уже в
    формате «ЕСЛИ-ТО-ПОТОМУ ЧТО» и заземлён в графе). Иначе собираем шаблон из
    intervention/effect_target/mechanism — тоже только из переданных полей, без новых
    сущностей, поэтому постпроверка домена всегда проходит.
    """

    def phrase(self, pattern_fields: dict) -> PhrasedCard:
        baseline = pattern_fields.get("baseline") or {}
        if baseline.get("if") and baseline.get("then") and baseline.get("because"):
            return PhrasedCard(
                **{
                    "if": baseline["if"],
                    "then": baseline["then"],
                    "because": baseline["because"],
                }
            )
        intervention = (
            pattern_fields.get("intervention")
            or pattern_fields.get("subject")
            or "воздействие"
        )
        target = (
            pattern_fields.get("effect_target")
            or pattern_fields.get("target")
            or pattern_fields.get("kpi")
            or "KPI"
        )
        mechanism = pattern_fields.get("mechanism", "механизм из цепочки доказательств")
        return PhrasedCard(
            **{
                "if": f"применить «{intervention}»",
                "then": f"улучшится «{target}»",
                "because": mechanism,
            }
        )


class FakeGraphRepository:
    """In-memory граф на чистом Python (без NetworkX) с рабочими запросами.

    Полноценная fake-реализация порта: на ней собираются и тестируются домен и
    фронт. Реальная версия — NetworkX MultiDiGraph с тем же контрактом.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []

    # --- запись ---
    def add_nodes(self, nodes: list[Node]) -> None:
        for node in nodes:
            self._nodes[node.id] = node

    def add_edges(self, edges: list[Edge]) -> None:
        self._edges.extend(edges)

    # --- чтение ---
    @property
    def nodes(self) -> list[Node]:
        return list(self._nodes.values())

    @property
    def edges(self) -> list[Edge]:
        return list(self._edges)

    def query_paths(
        self, source: str, target: str, max_len: int = 3
    ) -> list[list[Edge]]:
        """Все простые направленные пути source→target длиной ≤ max_len (DFS)."""
        out: list[list[Edge]] = []

        def dfs(node: str, path: list[Edge], visited: set[str]) -> None:
            if len(path) > max_len:
                return
            if node == target and path:
                out.append(list(path))
                return
            for edge in self._edges:
                if edge.source == node and edge.target not in visited:
                    dfs(edge.target, path + [edge], visited | {edge.target})

        dfs(source, [], {source})
        return out

    def neighbors(self, node_id: str) -> list[Node]:
        """Узлы, исходящие из node_id (по направленным рёбрам)."""
        ids = {e.target for e in self._edges if e.source == node_id}
        ids |= {e.source for e in self._edges if e.target == node_id}
        return [self._nodes[i] for i in sorted(ids) if i in self._nodes]

    def conflicting_edges(self) -> list[tuple[Edge, Edge]]:
        """Пары рёбер один source→target с противоположным знаком (разные годы)."""
        pairs: list[tuple[Edge, Edge]] = []
        for i in range(len(self._edges)):
            for j in range(i + 1, len(self._edges)):
                a, b = self._edges[i], self._edges[j]
                if (
                    a.source == b.source
                    and a.target == b.target
                    and a.sign != b.sign
                    and "0" not in (a.sign, b.sign)
                ):
                    pairs.append((a, b))
        return pairs

    def failure_nodes(self) -> list[Node]:
        """Узлы-провалы (кладбище)."""
        return [n for n in self._nodes.values() if n.type == "failure"]

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def all_nodes(self) -> list[Node]:
        return list(self._nodes.values())

    def all_edges(self) -> list[Edge]:
        return list(self._edges)

    def out_edges(self, node_id: str) -> list[Edge]:
        """Исходящие рёбра node_id→* (направленные)."""
        return [e for e in self._edges if e.source == node_id]

    def in_edges(self, node_id: str) -> list[Edge]:
        """Входящие рёбра *→node_id (направленные)."""
        return [e for e in self._edges if e.target == node_id]

    # --- персист ---
    def save(self, path: Path) -> None:
        payload = {
            "nodes": [n.model_dump() for n in self._nodes.values()],
            "edges": [e.model_dump() for e in self._edges],
        }
        Path(path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self, path: Path) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self._nodes = {n["id"]: Node(**n) for n in payload.get("nodes", [])}
        self._edges = [Edge(**e) for e in payload.get("edges", [])]


class FakeResearchAgent:
    """Фиксированный прогон агента из фикстур (scout/chat) — без сети и ключей."""

    def run(self, mission: Mission, input: dict) -> AgentResult:
        if mission == "scout":
            data = _load_fixture("agent_result_scout.json")
        else:
            data = _load_fixture("agent_result_chat.json")
        assert isinstance(data, dict)
        return AgentResult(**data)


__all__ = [
    "FakeOcr",
    "FakeFactExtractor",
    "FakeCardPhrasing",
    "FakeGraphRepository",
    "FakeResearchAgent",
]
