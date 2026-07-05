from __future__ import annotations

import os
from pathlib import Path


class Settings:

    RUNS_DIR = Path(os.environ.get("WEBAPP_RUNS_DIR", "outputs/runs"))

    MAX_KPI_LEN = 800
    DEFAULT_MAX_CHUNKS = int(os.environ.get("WEBAPP_MAX_CHUNKS", "18"))

    DEFAULT_MAX_HYPS = int(os.environ.get("WEBAPP_MAX_HYPS", "15"))

    SEARCH_BACKEND = os.environ.get("WEBAPP_SEARCH", "auto")

    LOCAL_ONLY = True

settings = Settings()
