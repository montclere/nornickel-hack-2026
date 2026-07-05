from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from webapp.config import settings

_RUN_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")

def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]

def run_dir(run_id: str) -> Path:
    if not _RUN_ID_RE.fullmatch(str(run_id or "")):
        return settings.RUNS_DIR / "__invalid__"
    return settings.RUNS_DIR / run_id

def ensure_run(run_id: str) -> Path:
    d = run_dir(run_id)
    (d / "sources" / "data").mkdir(parents=True, exist_ok=True)
    (d / "sources" / "knowledge").mkdir(parents=True, exist_ok=True)
    return d

def run_exists(run_id: str) -> bool:
    return run_dir(run_id).is_dir()

def save_json(run_id: str, name: str, data) -> Path:
    p = run_dir(run_id) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return p

def load_json(run_id: str, name: str):
    p = run_dir(run_id) / name
    if not p.exists():
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

def list_runs() -> list:
    if not settings.RUNS_DIR.exists():
        return []
    out = []
    for d in sorted(settings.RUNS_DIR.iterdir(), reverse=True):
        if d.is_dir():
            meta = None
            try:
                meta = json.load(open(d / "context.json", encoding="utf-8"))
            except Exception:
                pass
            out.append({"run_id": d.name, "kpi": (meta or {}).get("kpi", ""),
                        "timestamp": (meta or {}).get("timestamp", "")})
    return out

def resolve_source(run_id: str, rel_path: str) -> Path | None:
    base = (run_dir(run_id) / "sources").resolve()
    try:
        target = (base / rel_path).resolve()
    except (ValueError, OSError):
        return None
    if base not in target.parents and target != base:
        return None
    return target if target.is_file() else None
