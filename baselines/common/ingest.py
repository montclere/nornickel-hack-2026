# -*- coding: utf-8 -*-
"""Авто-приём материалов: PDF / XLSX / DOCX / TXT → единый список фрагментов.

Человек кладёт файлы в папку — здесь они автоматически парсятся, БЕЗ ручной схемы.
Каждый фрагмент несёт провенанс: {text, source, locator} (файл + страница/лист/абзац).

PDF: pymupdf (текстовый слой; для сканов без слоя — заглушка-предупреждение об OCR).
XLSX: openpyxl → строки листа как «källa: Лист!A5».
DOCX/TXT: stdlib.
"""
from __future__ import annotations

import glob
import html
import os
import re
import zipfile


def ingest_dir(path, exts=(".pdf", ".xlsx", ".docx", ".txt")):
    files = []
    for e in exts:
        files += glob.glob(os.path.join(path, "**", f"*{e}"), recursive=True)
    chunks = []
    for f in sorted(set(files)):
        chunks += ingest_file(f)
    return chunks


def ingest_file(path):
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)
    if ext == ".pdf":
        return _pdf(path, name)
    if ext == ".xlsx":
        return _xlsx(path, name)
    if ext == ".docx":
        return _docx(path, name)
    if ext == ".txt":
        return [{"text": open(path, encoding="utf-8", errors="ignore").read(),
                 "source": name, "locator": name, "kind": "prose"}]
    return []


def _pdf(path, name):
    import fitz  # pymupdf
    out = []
    doc = fitz.open(path)
    for i in range(doc.page_count):
        t = doc[i].get_text().strip()
        if len(t) >= 40:
            out.append({"text": t, "source": name, "locator": f"{name}:стр.{i + 1}",
                        "kind": "prose"})
    if not out:  # скан без текстового слоя
        out.append({"text": "", "source": name, "locator": name,
                    "needs_ocr": True, "kind": "prose"})
    return out


def _xlsx(path, name):
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
            # лист целиком как один фрагмент (структура сохранена построчно)
            out.append({"text": "\n".join(rows), "source": name,
                        "locator": f"{name}:{ws.title}", "kind": "table"})
    return out


def _docx(path, name):
    z = zipfile.ZipFile(path)
    xml = z.read("word/document.xml").decode("utf-8", "ignore")
    text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml)))
    paras = [p.strip() for p in text.splitlines() if len(p.strip()) > 3]
    return [{"text": "\n".join(paras), "source": name, "locator": name, "kind": "prose"}]


def split_chunks(chunks, max_chars=3500):
    """Порезать длинные ПРОЗАИЧЕСКИЕ фрагменты на куски по абзацам (для окна LLM).
    Таблицы НЕ дробим (лист целиком = один диагностический контекст; при извлечении
    берётся первые ~6000 символов), иначе один лист даёт много дублей-вызовов LLM."""
    out = []
    for c in chunks:
        t = c.get("text", "")
        if c.get("kind") == "table" or len(t) <= max_chars:
            out.append(c)
            continue
        buf, size = [], 0
        for para in t.split("\n"):
            if size + len(para) > max_chars and buf:
                out.append({**c, "text": "\n".join(buf)})
                buf, size = [], 0
            buf.append(para); size += len(para) + 1
        if buf:
            out.append({**c, "text": "\n".join(buf)})
    return out
