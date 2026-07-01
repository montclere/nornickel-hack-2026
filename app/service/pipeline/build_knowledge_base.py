"""Use-case: приём базы знаний.

PDF с текстовым слоем → текст напрямую; сканы/картинки → Ocr → markdown.
Затем нарезка на фрагменты и извлечение фактов (FactExtractor) → триплеты.
"""

from __future__ import annotations

from pathlib import Path

from app.service.entities import Chunk, Document, Triplet
from app.service.interfaces import FactExtractor, Ocr


class BuildKnowledgeBase:
    def __init__(self, ocr: Ocr, fact_extractor: FactExtractor) -> None:
        self.ocr = ocr
        self.fact_extractor = fact_extractor

    def execute(self, documents: list[Document]) -> list[Triplet]:
        """Прогнать корпус: (OCR при необходимости) → чанкинг → извлечение фактов."""
        triplets: list[Triplet] = []
        for doc in documents:
            text = self._read_text(doc)
            for chunk in self._chunk(doc, text):
                triplets.extend(self.fact_extractor.extract(chunk))
        return triplets

    def _read_text(self, doc: Document) -> str:
        """Текст документа: скан → через OCR, иначе — текстовый слой напрямую."""
        if doc.is_scanned and doc.source_path:
            return self.ocr.parse(Path(doc.source_path)).markdown
        return doc.text or ""

    def _chunk(self, doc: Document, text: str) -> list[Chunk]:
        """Нарезка документа на фрагменты с заголовком источника (название + год).

        Заголовок даёт экстрактору год факта (его часто нет в самом абстракте) и
        остаётся частью текста — цитатный гейт по нему срабатывает корректно.

        TODO: реальный чанкер (по абзацам/окнам с перекрытием). Пока — один
        фрагмент на документ (абстракты/отчёты короткие).
        """
        if not text:
            return []
        body = f"[Источник: {doc.title}; год: {doc.year}]\n\n{text}"
        return [Chunk(id=f"{doc.id}::0", doc_id=doc.id, text=body, position=0)]
