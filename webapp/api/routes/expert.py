# -*- coding: utf-8 -*-
"""Страница «Эксперт»: просмотр и правка ОБЩЕЙ базы вердиктов (feedback.json).

База персистентна: вердикты действуют на все будущие запуски (веб и CLI), пока их
не изменить/удалить здесь. Тонкий слой над factory.feedback — никакой своей логики."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))
router = APIRouter(tags=["expert"])

_KEY_FIELDS = ("fabric", "size_class", "family", "intervention", "target_element")


@router.get("/expert", response_class=HTMLResponse)
def expert_page(request: Request):
    from factory.config import FEEDBACK_PATH
    from factory.feedback import load_feedback
    return TEMPLATES.TemplateResponse(request, "expert.html", {
        "entries": load_feedback(), "feedback_path": FEEDBACK_PATH})


@router.post("/api/feedback")
def feedback_upsert(fabric: str = Form(...), size_class: str = Form(...),
                    family: str = Form(...), intervention: str = Form(...),
                    target_element: str = Form(...),
                    verdict: str = Form(...), note: str = Form("")):
    from factory.feedback import upsert
    try:
        saved = upsert({"fabric": fabric, "size_class": size_class, "family": family,
                        "intervention": intervention, "target_element": target_element,
                        "verdict": verdict, "note": note})
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return {"ok": True, "verdict": saved["verdict"]}


@router.post("/api/feedback/delete")
def feedback_delete(fabric: str = Form(...), size_class: str = Form(...),
                    family: str = Form(...), intervention: str = Form(...),
                    target_element: str = Form(...)):
    from factory.feedback import remove
    gone = remove({"fabric": fabric, "size_class": size_class, "family": family,
                   "intervention": intervention, "target_element": target_element})
    if not gone:
        raise HTTPException(404, "запись не найдена")
    return {"ok": True}
