"""Источник реальных статей из OpenAlex.

OpenAlex отдаёт абстракт не текстом, а инвертированным индексом
({слово: [позиции]}) — восстанавливаем в обычный текст. Документы без абстракта
отбраковываются (нечего извлекать). HTTP-клиент инжектируется (тесты подменяют
его MockTransport — без сети).
"""

from __future__ import annotations

import time

import httpx

from app.service.entities import Document

OPENALEX_WORKS = "https://api.openalex.org/works"

# запросы по флотации Cu-Ni руд
DEFAULT_QUERIES: list[str] = [
    "flotation copper nickel ore",
    "pentlandite flotation collector",
    "nickel recovery flotation reagent",
    "depressant Cu-Ni flotation",
]

_SELECT = "id,title,publication_year,abstract_inverted_index,primary_location,doi"


def reconstruct_abstract(inverted: dict | None) -> str | None:
    """Инвертированный индекс OpenAlex → связный текст абстракта."""
    if not inverted:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    if not positions:
        return None
    positions.sort(key=lambda p: p[0])
    return " ".join(word for _, word in positions)


def _short_id(openalex_id: str) -> str:
    """'https://openalex.org/W123' → 'W123'."""
    return openalex_id.rstrip("/").rsplit("/", 1)[-1]


def work_to_document(work: dict) -> Document | None:
    """OpenAlex work → Document. None, если нет заголовка/года/абстракта."""
    title = work.get("title")
    year = work.get("publication_year")
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    if not title or not year or not abstract:
        return None
    location = work.get("primary_location") or {}
    url = location.get("landing_page_url") or work.get("doi") or work.get("id")
    return Document(
        id=f"openalex_{_short_id(work.get('id', ''))}",
        title=title,
        year=int(year),
        source="openalex",
        url=url,
        is_synthetic=False,
        is_scanned=False,
        text=abstract,
    )


class OpenAlexSource:
    """Тонкая обёртка над OpenAlex works API → список Document."""

    def __init__(
        self,
        *,
        mailto: str = "phoenix-hackathon@example.com",
        per_page: int = 50,
        queries: list[str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.mailto = mailto
        self.per_page = per_page
        self.queries = queries or DEFAULT_QUERIES
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=30.0, headers={"User-Agent": f"phoenix-hackathon ({self.mailto})"}
            )
        return self._client

    def _fetch_query(self, query: str) -> list[dict]:
        params = {
            "search": query,
            "filter": "has_abstract:true,language:en",
            "per-page": self.per_page,
            "select": _SELECT,
            "mailto": self.mailto,
        }
        last: Exception | None = None
        for attempt in range(3):  # OpenAlex иногда отдаёт 5xx — пара повторов
            try:
                resp = self._get_client().get(OPENALEX_WORKS, params=params)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"retryable {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                return resp.json().get("results", [])
            except httpx.HTTPError as exc:
                last = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise last  # type: ignore[misc]

    def search(self, query: str, *, limit: int = 5) -> list[Document]:
        """Один поисковый запрос → до `limit` статей с абстрактом (для агента)."""
        docs: list[Document] = []
        for work in self._fetch_query(query):
            doc = work_to_document(work)
            if doc is not None:
                docs.append(doc)
            if len(docs) >= limit:
                break
        return docs

    def fetch(self, *, max_docs: int = 200) -> list[Document]:
        """Прогнать все запросы, смапить в Document, дедуплицировать по id."""
        seen: dict[str, Document] = {}
        for query in self.queries:
            for work in self._fetch_query(query):
                doc = work_to_document(work)
                if doc is None or doc.id in seen:
                    continue
                seen[doc.id] = doc
                if len(seen) >= max_docs:
                    break
            if len(seen) >= max_docs:
                break
        return list(seen.values())

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None


__all__ = [
    "OpenAlexSource",
    "reconstruct_abstract",
    "work_to_document",
    "DEFAULT_QUERIES",
    "OPENALEX_WORKS",
]
