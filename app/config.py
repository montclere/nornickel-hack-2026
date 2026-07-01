"""Конфигурация: пути, пороги, имена моделей, режимы сборки.

Режим читается из аргумента `build(...)` либо из переменных окружения. Каждый
адаптер переключается независимо (`mix`-режим) — напр. OCR=fake, остальное real:

    PHOENIX_MODE=real PHOENIX_OCR=fake  →  всё real, кроме OCR.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["fake", "real", "mix"]

# --- пути (репозиторий-относительные) ----------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SCANS_DIR = DATA_DIR / "scans"
FIXTURES_DIR = ROOT_DIR / "fixtures"
OUTPUTS_DIR = ROOT_DIR / "outputs"


def _load_dotenv(path: Path) -> None:
    """Подтянуть ключи из .env (gitignored) в окружение, не переопределяя заданные.

    Минимальный лоадер без зависимостей: KEY=VALUE по строкам, # — комментарий.
    Делает GROQ_API_KEY/ANTHROPIC_API_KEY доступными и скриптам, и uvicorn.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT_DIR / ".env")

# имена переменных окружения для покомпонентного переключения (mix-режим)
_COMPONENT_ENV = {
    "ocr": "PHOENIX_OCR",
    "extractor": "PHOENIX_EXTRACT",
    "embeddings": "PHOENIX_EMBED",
    "graph": "PHOENIX_GRAPH",
    "phrasing": "PHOENIX_PHRASING",
    "agent": "PHOENIX_AGENT",
}


def _env_mode(var: str) -> Mode | None:
    val = os.getenv(var)
    if val in ("fake", "real", "mix"):
        return val  # type: ignore[return-value]
    return None


class Settings(BaseModel):
    """Контракт конфигурации. Значения по умолчанию рассчитаны на оффлайн-fake."""

    mode: Mode = "fake"
    # покомпонентные переопределения (для mix); None → следовать глобальному mode
    component_modes: dict[str, Mode] = Field(default_factory=dict)

    # пороги домена
    cosine_threshold: float = 0.87  # склейка синонимов сущностей
    max_path_len: int = 3  # глубина поиска путей в графе (генератор разрывов)

    # имена моделей (адаптеры infrastructure)
    ocr_model: str = "baidu/Unlimited-OCR"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # извлечение фактов — через OpenAI-совместимый API (по умолчанию Groq);
    # base_url/модель меняются под другого провайдера без правок кода.
    llm_base_url: str = "https://api.groq.com/openai/v1"
    extractor_model: str = "llama-3.3-70b-versatile"
    phrasing_model: str = "claude-opus-4-8"  # качество формулировок карточек
    agent_model: str = "claude-opus-4-8"

    # пути
    data_dir: Path = DATA_DIR
    scans_dir: Path = SCANS_DIR
    fixtures_dir: Path = FIXTURES_DIR
    outputs_dir: Path = OUTPUTS_DIR

    def mode_for(self, component: str) -> Mode:
        """Режим для конкретного адаптера: переопределение → иначе глобальный."""
        return self.component_modes.get(component, self.mode)


def load_settings(mode: Mode | None = None) -> Settings:
    """Собрать Settings из аргумента/окружения.

    Приоритет: явный аргумент `mode` > `PHOENIX_MODE` > "fake".
    Поверх — покомпонентные `PHOENIX_*` (для mix-режима).
    """
    global_mode: Mode = mode or _env_mode("PHOENIX_MODE") or "fake"
    component_modes: dict[str, Mode] = {}
    for component, var in _COMPONENT_ENV.items():
        override = _env_mode(var)
        if override is not None:
            component_modes[component] = override
    return Settings(mode=global_mode, component_modes=component_modes)


__all__ = [
    "Mode",
    "Settings",
    "load_settings",
    "ROOT_DIR",
    "DATA_DIR",
    "SCANS_DIR",
    "FIXTURES_DIR",
    "OUTPUTS_DIR",
]
