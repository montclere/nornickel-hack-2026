from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from webapp.infra import storage

_HTML = "text/html; charset=utf-8"

router = APIRouter(tags=["files"])

@router.get("/runs/{run_id}/sources/{path:path}")
def get_source(run_id: str, path: str):
    p = storage.resolve_source(run_id, path)
    if p is None:
        raise HTTPException(404, "файл не найден")

    return FileResponse(p, content_disposition_type="inline")

@router.get("/runs/{run_id}/report/{name}")
def get_report(run_id: str, name: str, dl: bool = False):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400, "недопустимое имя отчёта")
    p = storage.run_dir(run_id) / name
    if not p.is_file() or p.suffix.lower() not in (".html", ".json", ".csv", ".pdf", ".docx"):
        raise HTTPException(404, "отчёт не найден")
    media = _HTML if p.suffix.lower() == ".html" else None

    return FileResponse(p, media_type=media, filename=name,
                        content_disposition_type=("attachment" if dl else "inline"))
