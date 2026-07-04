# -*- coding: utf-8 -*-
"""Хранилище прогонов: изоляция по run_id, безопасное разрешение путей к исходникам.

Каждый прогон — папка `outputs/runs/<run_id>/` (эфемерно, без БД):
  sources/data/…        загруженные ДАННЫЕ фабрик (state) — наружу не уходят
  sources/knowledge/…   загруженные ЗНАНИЯ (reference)
  result.json           сериализованные гипотезы (export.serialize) для рендера
  context.json          что использовано + пути (для кликабельных источников)
  metrics.json          телеметрия прогона
  <fabric>_гипотезы.html, литература_гипотезы.html, glossary.html
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from webapp.config import settings


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def run_dir(run_id: str) -> Path:
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
            except Exception:  # noqa: BLE001
                pass
            out.append({"run_id": d.name, "kpi": (meta or {}).get("kpi", ""),
                        "timestamp": (meta or {}).get("timestamp", "")})
    return out


def resolve_source(run_id: str, rel_path: str) -> Path | None:
    """Безопасно разрешить путь к исходнику ВНУТРИ sources прогона (без выхода наружу).
    Возвращает Path или None, если путь вне песочницы/не существует."""
    base = (run_dir(run_id) / "sources").resolve()
    try:
        target = (base / rel_path).resolve()
    except (ValueError, OSError):
        return None
    if base not in target.parents and target != base:
        return None                    # попытка выйти за пределы sources — отказ
    return target if target.is_file() else None
