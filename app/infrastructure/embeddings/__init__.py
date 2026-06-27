"""Эмбеддинги и нормализация сущностей домена.

SbertEmbedding — мультиязычные векторы (sentence-transformers, ленивый импорт).
EntityNormalizer склеивает синонимы: сначала канонический словарь домена
(Ni/никель/nickel → "Ni"), затем — по косинусу ≥ порога для имён вне словаря.
"""

from app.infrastructure.embeddings.sbert import (
    CANONICAL_DICT,
    EntityNormalizer,
    Normalization,
    SbertEmbedding,
)

__all__ = ["SbertEmbedding", "EntityNormalizer", "Normalization", "CANONICAL_DICT"]
