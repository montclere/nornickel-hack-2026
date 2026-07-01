"""Тест изоляции чистого ядра.

Гарантирует главный инвариант проекта: внутри `app/service/domain/**` нет импорта
из `app.infrastructure` и `app.api`. Именно это даёт детерминированность ядра
(LLM/сеть/БД физически недоступны изнутри генерации/скоринга).

Дублирует контракт import-linter из pyproject.toml, но не требует его установки.
"""

from __future__ import annotations

import ast
from pathlib import Path

DOMAIN_DIR = Path(__file__).resolve().parent.parent / "app" / "service" / "domain"
FORBIDDEN = ("app.infrastructure", "app.api")


def _module_imports(source: str, filename: str = "<src>") -> list[str]:
    """Все импортируемые модули в исходнике (import X и from X import ...)."""
    tree = ast.parse(source, filename=filename)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def find_forbidden_imports(source: str, filename: str = "<src>") -> list[str]:
    """Импорты из запрещённых пакетов (точное совпадение или подпакет)."""
    return [
        mod
        for mod in _module_imports(source, filename)
        if any(mod == f or mod.startswith(f + ".") for f in FORBIDDEN)
    ]


def test_domain_has_no_infrastructure_or_api_imports():
    violations: dict[str, list[str]] = {}
    for path in DOMAIN_DIR.rglob("*.py"):
        bad = find_forbidden_imports(path.read_text(encoding="utf-8"), str(path))
        if bad:
            violations[str(path)] = bad
    assert not violations, f"Чистое ядро тянет запрещённые импорты: {violations}"


def test_detector_catches_violation():
    """Сам детектор реально ловит запрещённый импорт (positive control)."""
    bad_source = (
        "from app.infrastructure.fakes import FakeOcr\n"
        "import app.api.routes\n"
        "from app.service.entities import Node\n"  # это разрешено
    )
    flagged = find_forbidden_imports(bad_source)
    assert "app.infrastructure.fakes" in flagged
    assert "app.api.routes" in flagged
    assert "app.service.entities" not in flagged


def test_detector_passes_clean_source():
    clean_source = (
        "from app.service.entities import Node, Edge\n"
        "from app.service.interfaces import GraphRepository\n"
        "import networkx\n"
    )
    assert find_forbidden_imports(clean_source) == []
