# -*- coding: utf-8 -*-
"""Экспорт из веба: те же писатели factory/export.py (PDF/DOCX/CSV/JSON/Jira) поверх
result.json — который и есть сериализация serialize(), т.е. ядро НЕ дублируется.
Файлы собираются лениво в папке запуска и отдаются на скачивание."""
from __future__ import annotations

import csv

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from webapp.infra import storage

router = APIRouter(tags=["export"])

# формат → (функция factory.export, расширение файла)
_WRITERS = {
    "json": ("write_json", "json"),
    "csv": ("write_csv", "csv"),
    "pdf": ("write_pdf", "pdf"),
    "docx": ("write_docx", "docx"),
    "tasks": ("write_tasks_csv", "csv"),      # CSV под импортёр Jira
}


def _fabric(run_id: str, fi: int) -> dict:
    result = storage.load_json(run_id, "result.json")
    if not result:
        raise HTTPException(404, "результаты не найдены")
    fabrics = result.get("fabrics") or []
    if not (0 <= fi < len(fabrics)):
        raise HTTPException(404, "фабрика не найдена")
    return fabrics[fi]


@router.get("/runs/{run_id}/export/summary")
def export_summary(run_id: str):
    """Сводка запуска по всем фабрикам (CSV, ';' + utf-8-sig — открывается Excel)."""
    result = storage.load_json(run_id, "result.json")
    if not result:
        raise HTTPException(404, "результаты не найдены")
    out = storage.run_dir(run_id) / "export"
    out.mkdir(exist_ok=True)
    path = out / "сводка.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["kpi", "фабрика", "целевой_элемент", "гипотез",
                    "топ_вмешательство", "топ_класс", "impact_топ_%", "потенциал_топ3_%"])
        for fb in result.get("fabrics") or []:
            meta, hyps = fb.get("meta", {}), fb.get("hypotheses", [])
            top = hyps[0] if hyps else {}
            w.writerow([result.get("kpi", ""), meta.get("fabric", ""),
                        meta.get("target_element", ""), len(hyps),
                        top.get("intervention", ""), top.get("size_class", ""),
                        round(top.get("metrics", {}).get("impact", 0) * 100) if top else "",
                        meta.get("kpi_potential_top3_pct", "")])
    return FileResponse(path, filename="сводка.csv", media_type="text/csv")


@router.get("/runs/{run_id}/export/{fi}/{fmt}")
def export_fabric(run_id: str, fi: int, fmt: str):
    if fmt not in _WRITERS:
        raise HTTPException(422, f"неизвестный формат «{fmt}»; "
                                 f"доступны: {', '.join(_WRITERS)}")
    data = _fabric(run_id, fi)
    from factory import export as ex
    fn_name, ext = _WRITERS[fmt]
    base = (data.get("meta", {}).get("fabric") or "гипотезы")
    out = storage.run_dir(run_id) / "export"
    out.mkdir(exist_ok=True)
    suffix = "_задачи" if fmt == "tasks" else "_гипотезы"
    path = out / f"{base}{suffix}.{ext}"
    try:
        getattr(ex, fn_name)(data, str(path))
    except RuntimeError as e:                 # напр. нет кириллического шрифта для PDF
        raise HTTPException(500, str(e)) from None
    return FileResponse(path, filename=path.name)
