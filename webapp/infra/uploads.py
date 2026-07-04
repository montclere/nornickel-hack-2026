# -*- coding: utf-8 -*-
"""Приём загрузок (multipart) с разделением на ДАННЫЕ (data/state) и ЗНАНИЯ
(knowledge/reference). Без лимитов на размер/типы: ingest сам пропускает неизвестные
форматы. Сохраняем ОТНОСИТЕЛЬНЫЙ путь (для загруженных папок), чтобы не терять структуру."""
from __future__ import annotations

import os


class UploadError(ValueError):
    pass


def _safe_rel(name: str) -> str:
    """Относительный путь файла (браузер шлёт имя папки в filename при drag-drop папки),
    очищенный от выхода наверх/абсолютных путей."""
    name = (name or "").replace("\\", "/")
    parts = [p for p in name.split("/") if p not in ("", ".", "..")]
    return "/".join(parts) or "file"


# роль загрузки → подпапка в sources/. Схемы кладём ВНУТРЬ data («данные фабрики»):
# ingest по имени папки даст им роль state, а OCR-ветка подхватит картинки как сканы
_ROLE_DIRS = {"data": "data", "knowledge": "knowledge", "schemes": "data/схемы"}


async def save_group(run_id: str, files, role: str) -> list:
    """Сохранить группу файлов под sources/<подпапка роли>/. role ∈ {data, knowledge,
    schemes}. Возвращает список относительных путей (от sources/)."""
    if role not in _ROLE_DIRS:
        raise UploadError(f"неизвестная роль загрузки: {role}")
    from webapp.infra import storage
    storage.ensure_run(run_id)
    base = storage.run_dir(run_id) / "sources" / _ROLE_DIRS[role]
    saved = []
    for f in files or []:
        if not getattr(f, "filename", ""):
            continue
        rel = _safe_rel(f.filename)
        data = await f.read()
        if not data:
            continue
        dest = base / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        saved.append(f"{_ROLE_DIRS[role]}/{rel}")
    return saved
