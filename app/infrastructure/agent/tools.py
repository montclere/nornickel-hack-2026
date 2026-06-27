"""Инструменты агента-разведчика.

Чистые функции над портом GraphRepository + источником литературы + экстрактором.
Агент дёргает их из узлов LangGraph; единственный персистентный эффект — Triplet,
прошедший цитатный гейт (в extract_from_doc через тот же GroqFactExtractor).
"""

from __future__ import annotations

from app.service.domain.graph_ops import resolve_kpi_node
from app.service.entities import Chunk, Document, Triplet
from app.service.interfaces import GraphRepository

_GAP_PRIORITY = {"failure": 0, "reagent": 1, "material": 2}


def find_gaps(repo: GraphRepository, kpi: str, *, max_len: int = 3, limit: int = 6) -> list[dict]:
    """Структурные пробелы вокруг KPI: узлы без пути к KPI (оборванные цепочки).

    Приоритет — провалы (кандидаты на реанимацию), затем реагенты и материалы.
    """
    kpi_id = resolve_kpi_node(repo, kpi)
    if kpi_id is None:
        return []
    gaps: list[dict] = []
    for node in repo.all_nodes():
        if node.id == kpi_id or node.type == "KPI":
            continue
        if node.type not in ("reagent", "material", "failure"):
            continue
        if not repo.query_paths(node.id, kpi_id, max_len):  # связи с KPI нет
            gaps.append({"node_id": node.id, "label": node.label, "type": node.type})
    gaps.sort(key=lambda g: (_GAP_PRIORITY.get(g["type"], 3), g["node_id"]))
    return gaps[:limit]


def search_literature(source, query: str, *, limit: int = 4) -> list[Document]:
    """Поиск статей по запросу (OpenAlex). Источник инжектируется (тесты — фейк)."""
    return source.search(query, limit=limit)


def fetch_text(doc: Document) -> str:
    """Полный текст источника. Сейчас — абстракт из OpenAlex (полнотекст — задел)."""
    return doc.text or ""


def extract_from_doc(doc: Document, extractor) -> list[Triplet]:
    """Извлечь триплеты из источника тем же экстрактором с цитатным гейтом (Промпт 2)."""
    text = f"[Источник: {doc.title}; год: {doc.year}]\n\n{fetch_text(doc)}"
    chunk = Chunk(id=f"{doc.id}::agent", doc_id=doc.id, text=text, position=0)
    return extractor.extract(chunk)


__all__ = ["find_gaps", "search_literature", "fetch_text", "extract_from_doc"]
