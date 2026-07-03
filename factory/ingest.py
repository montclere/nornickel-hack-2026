# -*- coding: utf-8 -*-
"""Универсальный приём разнородных материалов → фрагменты с провенансом.

Человек кладёт ЧТО УГОДНО (PDF/DOCX/TXT/XLSX/CSV) — здесь всё автоматически
разбирается в единый список Chunk. Структуру НЕ хардкодим: текст идёт как текст,
таблицы — как строки с координатами. Дальнейшее извлечение сущностей — в extract.py.

Chunk = {text, source, locator, kind: 'prose'|'table', role, meta}. meta несёт
доступные метаданные (файл, страница/лист, дата файла).

role — «состояние» (факты про КОНКРЕТНУЮ фабрику: измерения, отчёты, схемы этого
объекта) vs «справочное» (теория, best practices, методички — общее знание домена,
не про конкретную фабрику). Различаем ПО ПАПКЕ (конвенция путей — см. _infer_role):
кладите файлы состояния под папку `state`/`фабрики`/`fabrics`, справочные — под
`reference`/`справочники`/`методички`. Не удалось определить → «справочное» —
безопаснее по умолчанию, чем случайно выдать общую теорию за факт о фабрике.
Роль тегируется здесь, а используется (влияет на скоринг) в discover.py/kgraph.py.
"""
from __future__ import annotations

import csv
import glob
import html
import os
import re
import zipfile
from dataclasses import dataclass, field

from factory.config import MAX_CHUNK_CHARS

_STATE_DIR_HINTS = {"state", "fabrics", "фабрики", "состояние", "объект", "объекты"}
_REFERENCE_DIR_HINTS = {"reference", "справочники", "методички", "литература", "reference_materials"}


def _infer_role(path: str) -> str:
    parts = {p.lower() for p in os.path.normpath(path).split(os.sep)}
    if parts & _STATE_DIR_HINTS:
        return "state"
    if parts & _REFERENCE_DIR_HINTS:
        return "reference"
    return "reference"  # безопасный дефолт


@dataclass
class Chunk:
    text: str
    source: str
    locator: str
    kind: str = "prose"
    role: str = "reference"
    meta: dict = field(default_factory=dict)


def ingest(paths) -> list:
    """paths — файл, папка или список. Возвращает список Chunk по всем поддерж. файлам."""
    if isinstance(paths, str):
        paths = [paths]
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += glob.glob(os.path.join(p, "**", "*"), recursive=True)
        else:
            files.append(p)
    out = []
    for f in sorted(set(files)):
        if os.path.isfile(f):
            out += ingest_file(f)
    return out


def ingest_file(path: str) -> list:
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)
    meta = {"file": name, "mtime": _mtime(path)}
    role = _infer_role(path)
    try:
        if ext == ".pdf":
            return _pdf(path, name, meta, role)
        if ext == ".docx":
            return _docx(path, name, meta, role)
        if ext in (".txt", ".md"):
            return [Chunk(open(path, encoding="utf-8", errors="ignore").read(),
                          name, name, "prose", role, meta)]
        if ext == ".xlsx":
            return _xlsx(path, name, meta, role)
        if ext == ".csv":
            return _csv(path, name, meta, role)
    except Exception as e:  # noqa: BLE001
        return [Chunk("", name, name, "prose", role, {**meta, "error": str(e)})]
    return []


def _mtime(path):
    try:
        import datetime
        return datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
    except Exception:  # noqa: BLE001
        return None


def _pdf(path, name, meta, role):
    import fitz
    doc = fitz.open(path)
    out = []
    for i in range(doc.page_count):
        t = doc[i].get_text().strip()
        if len(t) >= 40:
            out.append(Chunk(t, name, f"{name}:стр.{i+1}", "prose", role,
                             {**meta, "page": i + 1}))
    if not out:
        out.append(Chunk("", name, name, "prose", role, {**meta, "needs_ocr": True}))
    return out


def _docx(path, name, meta, role):
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8", "ignore")
    text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml)))
    paras = [p.strip() for p in text.splitlines() if len(p.strip()) > 3]
    return [Chunk("\n".join(paras), name, name, "prose", role, meta)]


def _xlsx(path, name, meta, role):
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        rows = []
        for r, row in enumerate(ws.iter_rows(values_only=True), 1):
            vals = [str(c) for c in row if c not in (None, "")]
            if vals:
                rows.append(f"[{ws.title}!{r}] " + " | ".join(vals))
        if rows:
            out.append(Chunk("\n".join(rows), name, f"{name}:{ws.title}", "table", role,
                             {**meta, "sheet": ws.title}))
    return out


def _csv(path, name, meta, role):
    rows = []
    with open(path, encoding="utf-8", errors="ignore", newline="") as f:
        for i, row in enumerate(csv.reader(f), 1):
            if any(row):
                rows.append(f"[{i}] " + " | ".join(row))
    return [Chunk("\n".join(rows), name, name, "table", role, meta)] if rows else []


def split(chunks, max_chars=MAX_CHUNK_CHARS) -> list:
    """Резать длинные прозаические фрагменты по абзацам (окно LLM)."""
    out = []
    for c in chunks:
        if c.kind != "prose" or len(c.text) <= max_chars:
            out.append(c); continue
        buf, size = [], 0
        for para in c.text.split("\n"):
            if size + len(para) > max_chars and buf:
                out.append(Chunk("\n".join(buf), c.source, c.locator, c.kind, c.role, c.meta))
                buf, size = [], 0
            buf.append(para); size += len(para) + 1
        if buf:
            out.append(Chunk("\n".join(buf), c.source, c.locator, c.kind, c.role, c.meta))
    return out
