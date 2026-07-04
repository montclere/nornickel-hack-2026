# -*- coding: utf-8 -*-
"""Создание прогона: загрузка материалов (data/knowledge) + KPI + параметры → запуск ядра
в ФОНЕ (поток), с записью прогресса по этапам в status.json. Клиент уходит на экран
загрузки и опрашивает статус."""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from webapp.config import settings
from webapp.di import get_llm, get_search
from webapp.infra import storage, uploads
from webapp.interfaces import LLMClient, SearchClient

router = APIRouter(prefix="/api", tags=["runs"])


def _job(run_id, kpi, constraints, web_search, use_llm, max_chunks, llm, search):
    """Фоновая задача: гонит RunService, пишет прогресс/итог/ошибку в status.json."""
    from webapp.services.run_service import RunService

    def progress(text):
        st = storage.load_json(run_id, "status.json") or {"log": []}
        st["current"] = text
        st.setdefault("log", []).append(text)
        st["done"] = False
        storage.save_json(run_id, "status.json", st)

    def detail(text):
        """Мелкие строки хода работы (какая фабрика, что ищем) — в лог экрана
        загрузки, НЕ меняя текущий этап."""
        st = storage.load_json(run_id, "status.json") or {"log": []}
        st.setdefault("log", []).append(str(text))
        storage.save_json(run_id, "status.json", st)

    try:
        RunService(llm=llm, search=search).run(
            run_id, kpi, constraints=constraints, web_search=web_search, use_llm=use_llm,
            max_chunks=max_chunks, progress=progress, log=detail)
        st = storage.load_json(run_id, "status.json") or {}
        st.update({"current": "Готово", "done": True, "redirect": f"/runs/{run_id}"})
        storage.save_json(run_id, "status.json", st)
    except Exception as e:  # noqa: BLE001
        st = storage.load_json(run_id, "status.json") or {}
        st.update({"error": str(e), "done": True})
        storage.save_json(run_id, "status.json", st)


@router.post("/runs")
async def create_run(
    kpi: str = Form(...),
    constraints: str = Form(""),
    web_search: bool = Form(False),
    use_llm: bool = Form(True),
    max_chunks: int = Form(settings.DEFAULT_MAX_CHUNKS),
    data_files: list[UploadFile] = File(default=[]),
    knowledge_files: list[UploadFile] = File(default=[]),
    llm: LLMClient = Depends(get_llm),
    search: SearchClient = Depends(get_search),
):
    kpi = (kpi or "").strip()
    if not kpi:
        raise HTTPException(422, "KPI обязателен — без цели неясно, что оптимизировать")
    if len(kpi) > settings.MAX_KPI_LEN:
        raise HTTPException(422, f"KPI слишком длинный (>{settings.MAX_KPI_LEN})")

    run_id = storage.new_run_id()
    await uploads.save_group(run_id, data_files, "data")
    await uploads.save_group(run_id, knowledge_files, "knowledge")
    if not any((storage.run_dir(run_id) / "sources").rglob("*")):
        raise HTTPException(422, "материалы не загружены — добавьте файл или папку")

    storage.save_json(run_id, "status.json",
                      {"current": "постановка в очередь", "log": [], "done": False, "error": None})
    max_chunks = max(2, min(60, int(max_chunks)))
    constraints = (constraints or "").strip()[:settings.MAX_KPI_LEN]
    threading.Thread(target=_job, daemon=True,
                     args=(run_id, kpi, constraints, web_search, use_llm, max_chunks, llm, search)).start()
    return {"run_id": run_id, "redirect": f"/runs/{run_id}/loading"}


@router.post("/runs/{run_id}/feedback")
def save_feedback(run_id: str, fi: int = Form(...), rank: int = Form(...),
                  verdict: str = Form(...), note: str = Form("")):
    """Вердикт эксперта с карточки → общая база feedback.json (factory.feedback).
    Тот же механизм, что у импорта из CSV: следующий запуск (веб или CLI)
    применит вердикт автоматически — переранжирует, не скрывая гипотезу."""
    result = storage.load_json(run_id, "result.json")
    if not result:
        raise HTTPException(404, "результаты не найдены")
    fabrics = result.get("fabrics") or []
    if not (0 <= fi < len(fabrics)):
        raise HTTPException(404, "фабрика не найдена")
    hyp = next((h for h in fabrics[fi].get("hypotheses", []) if h.get("rank") == rank), None)
    if hyp is None:
        raise HTTPException(404, "гипотеза не найдена")

    from factory.feedback import upsert
    entry = {"fabric": fabrics[fi].get("meta", {}).get("fabric", ""),
             "size_class": hyp.get("size_class", ""), "family": hyp.get("family", ""),
             "intervention": hyp.get("intervention", ""),
             "target_element": hyp.get("target_element", ""),
             "verdict": verdict, "note": note}
    try:
        saved = upsert(entry)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return {"ok": True, "verdict": saved["verdict"], "note": saved.get("note", "")}


@router.get("/runs/{run_id}/status")
def run_status(run_id: str):
    st = storage.load_json(run_id, "status.json")
    if st is None:
        if storage.run_exists(run_id):
            return {"current": "готово", "done": True, "redirect": f"/runs/{run_id}"}
        raise HTTPException(404, "запуск не найден")
    return st
