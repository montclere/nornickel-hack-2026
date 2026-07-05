from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

from factory.config import RUN_CONFIG_PATH


@dataclass
class RunConfig:
    kpi: str
    materials_paths: list = field(default_factory=list)
    cache_path: str = ""
    max_chunks: int = 0
    timestamp: str = ""

def save_run_config(cfg: RunConfig, path: str = RUN_CONFIG_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(asdict(cfg), open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def load_run_config(path: str = RUN_CONFIG_PATH) -> RunConfig | None:
    if not os.path.exists(path):
        return None
    try:
        d = json.load(open(path, encoding="utf-8"))
        return RunConfig(**{k: v for k, v in d.items() if k in RunConfig.__dataclass_fields__})
    except (json.JSONDecodeError, TypeError, OSError):
        return None

def resolve_kpi(cli_kpi: str, kpi_file: str = RUN_CONFIG_PATH):
    if cli_kpi and cli_kpi.strip():
        return cli_kpi, "CLI (--kpi)"
    cfg = load_run_config(kpi_file)
    if cfg and cfg.kpi:
        when = f" от {cfg.timestamp}" if cfg.timestamp else ""
        return cfg.kpi, f"файл конфига {kpi_file} (создан flex.py{when})"
    return "", f"не найден ни в --kpi, ни в {kpi_file}"
