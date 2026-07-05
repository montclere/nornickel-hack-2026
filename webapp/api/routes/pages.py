from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from webapp.di import get_report_service
from webapp.infra import storage

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))

TEMPLATES.env.globals["static_v"] = int(time.time())
router = APIRouter(tags=["pages"])

@router.get("/glossary", response_class=HTMLResponse)
def glossary_page(request: Request, run_id: str | None = None):
    from factory.render.glossary import body_html
    return TEMPLATES.TemplateResponse(request, "glossary.html",
                                      {"body": body_html(), "run_id": run_id})

@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return TEMPLATES.TemplateResponse(request, "index.html", {"runs": storage.list_runs()})

@router.get("/runs/{run_id}/loading", response_class=HTMLResponse)
def loading_page(request: Request, run_id: str):
    if not storage.run_exists(run_id):
        raise HTTPException(404, "запуск не найден")
    return TEMPLATES.TemplateResponse(request, "loading.html", {"run_id": run_id})

@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str, rs=Depends(get_report_service)):
    if not storage.run_exists(run_id):
        raise HTTPException(404, "запуск не найден")
    result = rs.result(run_id) or {"fabrics": [], "reports": []}
    return TEMPLATES.TemplateResponse(request, "run.html", {
        "run_id": run_id, "result": result,
        "context": rs.context(run_id) or {}, "metrics": rs.metrics(run_id) or {}})

@router.get("/runs/{run_id}/lit/{rank}", response_class=HTMLResponse)
def lit_card_page(request: Request, run_id: str, rank: int,
                  rs=Depends(get_report_service)):
    got = rs.lit_hypothesis(run_id, rank)
    if not got:
        raise HTTPException(404, "гипотеза не найдена")
    result, hyp = got
    return TEMPLATES.TemplateResponse(request, "lit_card.html", {
        "run_id": run_id, "h": hyp, "result": result})

@router.get("/runs/{run_id}/hyp/{fi}/{rank}", response_class=HTMLResponse)
def card_page(request: Request, run_id: str, fi: int, rank: int,
              rs=Depends(get_report_service)):
    got = rs.hypothesis(run_id, fi, rank)
    if not got:
        raise HTTPException(404, "гипотеза не найдена")
    fabric, hyp = got

    from factory.evals.feedback import find_saved
    saved_fb = find_saved({**hyp, "fabric": fabric.get("meta", {}).get("fabric", "")})
    return TEMPLATES.TemplateResponse(request, "card.html", {
        "run_id": run_id, "fi": fi, "saved_fb": saved_fb,
        "fabric": fabric, "h": hyp, "meta": fabric.get("meta", {})})
