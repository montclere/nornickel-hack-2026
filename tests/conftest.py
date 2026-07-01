"""Общие хелперы тестов: загрузка фикстур."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import FIXTURES_DIR


def load_fixture(name: str):
    """Прочитать fixtures/<name> как JSON."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def load():
    return load_fixture
