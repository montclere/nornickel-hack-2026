"""Доменные исключения проекта «Феникс»."""

from __future__ import annotations


class PhoenixError(Exception):
    """Базовое исключение для всех ошибок проекта."""


class ConfigError(PhoenixError):
    """Неверная конфигурация / режим сборки контейнера."""


class HallucinationError(PhoenixError):
    """Цитата-доказательство триплета не найдена в исходном фрагменте дословно.

    Срабатывает в цитатном гейте извлечения фактов.
    """


class GraphNotBuiltError(PhoenixError):
    """Запрос к графу до того, как он построен/загружен."""


class SnapshotMismatchError(PhoenixError):
    """Генерация запущена не поверх ожидаемого снапшота графа."""


class PhrasingViolationError(PhoenixError):
    """CardPhrasing ввёл новую сущность/факт, которого нет в evidence_path."""


__all__ = [
    "PhoenixError",
    "ConfigError",
    "HallucinationError",
    "GraphNotBuiltError",
    "SnapshotMismatchError",
    "PhrasingViolationError",
]
