# -*- coding: utf-8 -*-
"""Отдача файлов прогона: загруженные ИСХОДНИКИ (для кликабельных цитат — открываются в
новой вкладке, PDF — на нужной странице через #page=N) и сгенерированные HTML-отчёты.

Пути разрешаются безопасно (storage.resolve_source, без выхода за пределы sources/)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from webapp.infra import storage

router = APIRouter(tags=["files"])


@router.get("/runs/{run_id}/sources/{path:path}")
def get_source(run_id: str, path: str):
    p = storage.resolve_source(run_id, path)
    if p is None:
        raise HTTPException(404, "файл не найден")
    # inline: браузер откроет PDF/картинку прямо во вкладке (на #page=N — на нужном месте).
    # content_disposition_type сам корректно кодирует кириллическое имя (RFC 5987).
    return FileResponse(p, content_disposition_type="inline")


@router.get("/runs/{run_id}/report/{name}")
def get_report(run_id: str, name: str):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "недопустимое имя отчёта")
    p = storage.run_dir(run_id) / name
    if not p.is_file() or p.suffix.lower() not in (".html", ".json", ".csv", ".pdf", ".docx"):
        raise HTTPException(404, "отчёт не найден")
    return FileResponse(p, content_disposition_type="inline")
