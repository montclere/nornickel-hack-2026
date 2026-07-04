# -*- coding: utf-8 -*-
"""HTML-страницы (Jinja2): стартовый экран загрузки, обзор прогона (карточки), деталь.
Графы рендерятся как inline-SVG (в готовых отчётах), интерактив — htmx + ванильный JS."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from webapp.di import get_report_service
from webapp.infra import storage

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))
router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return TEMPLATES.TemplateResponse(request, "index.html", {"runs": storage.list_runs()})


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str, rs=Depends(get_report_service)):
    if not storage.run_exists(run_id):
        raise HTTPException(404, "прогон не найден")
    result = rs.result(run_id) or {"fabrics": [], "reports": []}
    return TEMPLATES.TemplateResponse(request, "run.html", {
        "run_id": run_id, "result": result,
        "context": rs.context(run_id) or {}, "metrics": rs.metrics(run_id) or {}})


@router.get("/runs/{run_id}/hyp/{fi}/{rank}", response_class=HTMLResponse)
def card_page(request: Request, run_id: str, fi: int, rank: int,
              rs=Depends(get_report_service)):
    got = rs.hypothesis(run_id, fi, rank)
    if not got:
        raise HTTPException(404, "гипотеза не найдена")
    fabric, hyp = got
    return TEMPLATES.TemplateResponse(request, "card.html", {
        "run_id": run_id, "fi": fi,
        "fabric": fabric, "h": hyp, "meta": fabric.get("meta", {})})
