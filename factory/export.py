# -*- coding: utf-8 -*-
"""Экспорт гипотез: JSON / CSV / задачи (Jira) / PDF / DOCX. ДЕТЕРМИНИРОВАННО, без LLM.

Один слой сериализации (`serialize`) → плоские записи; все форматы — тонкие писатели
поверх НЕГО, поэтому числа/формулировки во всех файлах гарантированно совпадают с
HTML-отчётом (единый источник — Hypothesis из generator.py).

Форматы:
  json   — машиночитаемый контракт для внешних систем (API-обвязка садится поверх);
  csv    — таблица для эксперта (Excel, ';', utf-8-sig): правит/оценивает прямо в ней,
           последние колонки «вердикт_эксперта»/«комментарий_эксперта» — под обратную
           связь (реимпорт этих колонок — следующий шаг, см. PLAN.md);
  tasks  — формат задач: tasks.csv (импортируется в Jira: Summary/Priority/Labels/
           Description) + tasks.json (то же для API);
  pdf    — бизнес-отчёт (reportlab, шрифт ищется по системным путям Linux/macOS);
  docx   — тот же бизнес-отчёт для Word (собирается вручную через zipfile, без
           новых зависимостей — симметрично чтению docx в ingest.py).

Про «достижение KPI»: гипотезы НЕ проверены экспериментально, поэтому мы честно пишем
«потенциально адресует N% извлекаемых потерь» (метрика impact — факт из данных),
а не «KPI достигнут» — это соответствует ответу организаторов («на базовых знаниях
о работе оборудования или физики»).

Запуск:
    uv run python -m factory.export "materials/fabrics/ТОФ/Хвосты ТОФ_2.xlsx" \
        --kpi "снизить потери никеля" [--formats all|json,csv,tasks,pdf,docx] [--out-dir outputs]
    # либо флагом --export у основного пайплайна:  python -m factory ... --export all
"""
from __future__ import annotations

import csv
import html
import json
import os
import time
import zipfile

FORMATS = ("json", "csv", "tasks", "pdf", "docx")


# ─────────────────────────── сериализация (общий слой) ───────────────────────────

def serialize(hyps, profile=None, kpi: str = "") -> dict:
    """Гипотезы (+профиль) → {'meta':…, 'hypotheses':[записи]}. Единый источник
    для всех форматов. Поля читаются терпимо (getattr) — переживает эволюцию модели."""
    records = [_record(h) for h in hyps]
    totals: dict = {}
    for r in records:
        for sym, t in (r["metrics"].get("rec_tonnes") or {}).items():
            totals[sym] = round(totals.get(sym, 0.0) + (t or 0.0), 1)
    top3 = round(sum(r["metrics"].get("impact", 0.0) for r in records[:3]) * 100)
    return {
        "meta": {
            "fabric": getattr(profile, "fabric", "") if profile else "",
            "source": getattr(profile, "source", "") if profile else "",
            "schema": getattr(profile, "schema_name", "") if profile else "",
            "warnings": list(getattr(profile, "warnings", []) or []) if profile else [],
            "kpi": kpi,
            "target_element": records[0]["target_element"] if records else "",
            "n_hypotheses": len(records),
            "recoverable_tonnes_total": totals,      # факт из данных, по каждому металлу
            "kpi_potential_top3_pct": top3,          # честное «потенциально адресуют N%»
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "hypotheses": records,
    }


def _record(h) -> dict:
    g = lambda name, default="": getattr(h, name, default)
    # эксперимент теперь три поля (тест/метрика/критерий, см. generator.py); собираем в
    # одну строку для плоских форматов и оставляем структурно для JSON. Fallback на
    # старое поле experiment — на случай объектов до разбиения.
    exp = " | ".join(p for p in (
        f"Тест: {g('exp_test')}" if g("exp_test") else "",
        f"Метрика: {g('exp_metric')}" if g("exp_metric") else "",
        f"Критерий: {g('exp_criterion')}" if g("exp_criterion") else "",
    ) if p) or g("experiment")
    return {
        "rank": g("rank", 0),
        "size_class": g("size_class"),
        "family": g("family"),
        "intervention": g("intervention"),
        "alternatives": list(g("alternatives", []) or []),
        "dominant_form": g("dominant_form"),
        "target_element": g("target_element"),
        "diagnosis": g("diagnosis"),
        "statement_if": g("statement_if"),
        "statement_then": g("statement_then"),
        "statement_because": g("statement_because"),
        "experiment": exp,
        "exp_test": g("exp_test"), "exp_metric": g("exp_metric"),
        "exp_criterion": g("exp_criterion"),
        "roadmap": list(g("roadmap", []) or []),         # лаборатория→пилот→внедрение
        "evidence": list(g("evidence", []) or []),
        "sources": list(g("sources", []) or []),
        "violates_constraints": list(g("violates_constraints", []) or []),
        "literature": list(g("literature", []) or []),   # цитаты из выданного корпуса
        "world_practice": g("world_practice", None),
        "expert_feedback": g("expert_feedback", None),   # вердикт из feedback.json (если был)
        "metrics": dict(g("metrics", {}) or {}),
    }


# ─────────────────────────── json / csv ───────────────────────────

def write_json(data: dict, path: str) -> str:
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return path


# колонки CSV эксперта; две последние заполняет эксперт в Excel (вердикт: полезно /
# неверно / уже пробовали). Если фидбэк по гипотезе уже есть (feedback.json) — они
# ПРЕДЗАПОЛНЯЮТСЯ текущим значением: эксперт видит и правит, а не вспоминает.
# Реимпорт: python -m factory.feedback import <этот csv>
_CSV_HEADER = ["ранг", "фабрика", "класс", "семейство", "вмешательство",
               "целевой_элемент", "impact_%", "приоритет", "извлекаемо_т",
               "излечимость", "ясность", "реализуемость", "достоверность",
               "ЕСЛИ", "ТО", "ПОТОМУ_ЧТО", "эксперимент", "заземление_ячейки",
               "источники", "нарушает_ограничения", "мировая_практика_URL",
               "альтернативы", "вердикт_эксперта", "комментарий_эксперта"]


def write_csv(data: dict, path: str) -> str:
    """CSV для эксперта: ';' + utf-8-sig → русский Excel открывает двойным кликом."""
    meta = data["meta"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(_CSV_HEADER)
        for r in data["hypotheses"]:
            m = r["metrics"]
            wp = r.get("world_practice")
            w.writerow([
                r["rank"], meta["fabric"], r["size_class"], r["family"],
                r["intervention"], r["target_element"],
                round(m.get("impact", 0) * 100), m.get("priority", ""),
                "; ".join(f"{k}={v}" for k, v in (m.get("rec_tonnes") or {}).items()),
                m.get("addressability", ""), m.get("clarity", ""),
                m.get("feasibility", ""), m.get("confidence", ""),
                r["statement_if"], r["statement_then"], r["statement_because"],
                r["experiment"],
                " | ".join(f"{e.get('label','')}→{e.get('cell','')}" for e in r["evidence"]),
                "; ".join(r["sources"]),
                "; ".join(r["violates_constraints"]),
                (wp or {}).get("url", "") if isinstance(wp, dict) else "",
                "; ".join(r["alternatives"]),
                # поля эксперта: предзаполнены текущим фидбэком (round-trip), иначе пустые
                (r.get("expert_feedback") or {}).get("verdict", "").replace("_", " "),
                (r.get("expert_feedback") or {}).get("note", "")])
    return path


# ─────────────────────────── задачи (Jira-совместимо) ───────────────────────────

def _priority(rank: int) -> str:
    return {1: "Highest", 2: "High", 3: "High"}.get(rank, "Medium" if rank <= 5 else "Low")


def _task_description(r: dict, meta: dict) -> str:
    m = r["metrics"]
    wp = r.get("world_practice")
    lines = [
        f"KPI: {meta['kpi']}",
        f"ЕСЛИ: {r['statement_if']}",
        f"ТО: {r['statement_then']}",
        f"ПОТОМУ ЧТО: {r['statement_because']}",
        "",
        f"Потенциал: адресует {round(m.get('impact', 0)*100)}% извлекаемых потерь "
        f"{r['target_element']} по фабрике {meta['fabric']} (не проверено экспериментально).",
        f"Эксперимент: {r['experiment']}",
        "Дорожная карта: " + " → ".join(
            f"{s['stage']}) {s['name']} (критерий: {s['success']})"
            for s in r.get("roadmap", [])),
        "Заземление: " + "; ".join(f"{e.get('label','')} [{e.get('cell','')}]"
                                    for e in r["evidence"]),
        "Источники метода: " + "; ".join(r["sources"]),
    ]
    if isinstance(wp, dict) and wp.get("url"):
        lines.append(f"Мировая практика: {wp.get('practice','')} ({wp['url']})")
    if r["violates_constraints"]:
        lines.append("⚠ Нарушает ограничение запроса: " + "; ".join(r["violates_constraints"]))
    return "\n".join(lines)


def _tasks(data: dict) -> list:
    meta = data["meta"]
    out = []
    for r in data["hypotheses"]:
        out.append({
            "summary": f"[{meta['fabric']}] {r['intervention']} (класс {r['size_class']})",
            "issue_type": "Task",
            "priority": _priority(r["rank"]),
            "labels": [x for x in (meta["fabric"], r["family"].replace(" ", "_"),
                                   r["size_class"], r["target_element"]) if x],
            "description": _task_description(r, meta),
        })
    return out


def write_tasks_json(data: dict, path: str) -> str:
    json.dump({"kpi": data["meta"]["kpi"], "issues": _tasks(data)},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return path


def write_tasks_csv(data: dict, path: str) -> str:
    """CSV под импортёр Jira (запятая, кавычки): Summary/Issue Type/Priority/Labels/Description."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Summary", "Issue Type", "Priority", "Labels", "Description"])
        for t in _tasks(data):
            w.writerow([t["summary"], t["issue_type"], t["priority"],
                        " ".join(t["labels"]), t["description"]])
    return path


# ─────────────────────────── pdf (бизнес-отчёт) ───────────────────────────

# пары (обычный, жирный); первая существующая — в дело. Linux → DejaVu, macOS → Arial
_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Verdana.ttf",
     "/System/Library/Fonts/Supplemental/Verdana Bold.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
]


def _register_fonts():
    """Зарегистрировать кириллический шрифт из системных путей; None — не нашли."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for reg, bold in _FONT_CANDIDATES:
        if os.path.exists(reg) and os.path.exists(bold):
            pdfmetrics.registerFont(TTFont("XF", reg))
            pdfmetrics.registerFont(TTFont("XF-B", bold))
            return "XF", "XF-B"
    return None


def write_pdf(data: dict, path: str) -> str:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, PageTemplate,
                                    Paragraph, Spacer, Table, TableStyle)

    fonts = _register_fonts()
    if fonts is None:                     # без кириллического шрифта PDF выйдет кракозябрами
        raise RuntimeError("не найден TTF-шрифт с кириллицей (см. _FONT_CANDIDATES) — "
                           "PDF пропущен; остальные форматы не зависят от шрифтов")
    F, FB = fonts
    INK, TEAL, BLUE, MUTED, LINE = (colors.HexColor(c) for c in
                                    ("#12303f", "#0f9c95", "#1f6fd0", "#6b8593", "#dce6ec"))
    meta = data["meta"]
    E = lambda s: html.escape(str(s if s is not None else ""))

    base = dict(fontName=F, textColor=INK, leading=13, fontSize=9.5)
    st = {
        "title": ParagraphStyle("t", **{**base, "fontName": FB, "fontSize": 19, "leading": 22}),
        "sub": ParagraphStyle("s", **{**base, "fontSize": 9.5, "textColor": MUTED, "spaceAfter": 8}),
        "h2": ParagraphStyle("h2", **{**base, "fontName": FB, "fontSize": 12.5,
                                      "textColor": TEAL, "spaceBefore": 12, "spaceAfter": 3}),
        "h3": ParagraphStyle("h3", **{**base, "fontName": FB, "fontSize": 10.5,
                                      "textColor": BLUE, "spaceBefore": 10, "spaceAfter": 2}),
        "body": ParagraphStyle("b", **{**base, "spaceAfter": 4}),
        "small": ParagraphStyle("sm", **{**base, "fontSize": 8, "textColor": MUTED}),
        "cell": ParagraphStyle("c", **{**base, "fontSize": 8, "leading": 10}),
    }
    story = []
    P = lambda t, s="body": story.append(Paragraph(t, st[s]))

    # титул + KPI + честная сводка потенциала
    P(f"Фабрика гипотез · {E(meta['fabric'])}", "title")
    P(f"бизнес-отчёт · {E(meta['generated_at'])} · источник: {E(meta['source'])} · "
      f"схема: {E(meta['schema'])}", "sub")
    P(f"<b>KPI:</b> {E(meta['kpi'])}")
    tons = " · ".join(f"<b>{v} т</b> {E(k)}" for k, v in
                      meta["recoverable_tonnes_total"].items())
    P(f"Извлекаемого металла в хвостах (факт из отчёта): {tons}.")
    P(f"Топ-3 гипотезы потенциально адресуют <b>{meta['kpi_potential_top3_pct']}%</b> "
      f"извлекаемых потерь {E(meta['target_element'])} по фабрике. Оценка — из данных "
      f"отчёта (метрика impact); экспериментально не проверено — протокол проверки "
      f"приложен к каждой гипотезе.", "body")
    for w in meta["warnings"]:
        P(f"⚠ {E(w)}", "small")

    # сводная таблица ранжирования
    P("Ранжирование гипотез", "h2")
    el = meta["target_element"]
    rows = [["№", "класс", "семейство", "вмешательство", "impact",
             f"т {el}", "приоритет"]]
    for r in data["hypotheses"]:
        m = r["metrics"]
        rows.append([str(r["rank"]), r["size_class"],
                     Paragraph(E(r["family"]), st["cell"]),
                     Paragraph(E(r["intervention"]), st["cell"]),
                     f"{round(m.get('impact', 0)*100)}%",
                     str((m.get("rec_tonnes") or {}).get(el, "")),
                     str(m.get("priority", ""))])
    story.append(Table(rows, colWidths=[18, 52, 100, 170, 40, 45, 50], style=TableStyle([
        ("FONT", (0, 0), (-1, -1), F, 8), ("FONT", (0, 0), (-1, 0), FB, 8),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fbfc")]),
    ])))
    story.append(Spacer(1, 6))

    # карточки
    for r in data["hypotheses"]:
        m = r["metrics"]
        story.append(HRFlowable(width="100%", thickness=0.6, color=LINE,
                                spaceBefore=6, spaceAfter=2))
        P(f"#{r['rank']} · {E(r['intervention'])} — класс {E(r['size_class'])} "
          f"({round(m.get('impact', 0)*100)}% потерь {E(el)})", "h3")
        P(f"<b>ЕСЛИ:</b> {E(r['statement_if'])}")
        P(f"<b>ТО:</b> {E(r['statement_then'])}")
        P(f"<b>ПОТОМУ ЧТО:</b> {E(r['statement_because'])}")
        if r["violates_constraints"]:
            P(f"⚠ нарушает ограничение запроса: {E('; '.join(r['violates_constraints']))} "
              f"— приоритет занижен, гипотеза не скрыта", "small")
        P(f"<b>Эксперимент:</b> {E(r['experiment'])}")
        for s in r.get("roadmap", []):
            P(f"<b>Этап {s['stage']} — {E(s['name'])}:</b> {E(s['actions'])} · "
              f"<b>критерий перехода:</b> {E(s['success'])}", "small")
        ev = "; ".join(f"{e.get('label','')} [{e.get('cell','')}]" for e in r["evidence"])
        P(f"<b>Заземление (ячейки отчёта):</b> {E(ev)}", "small")
        P(f"<b>Источники метода:</b> {E('; '.join(r['sources']))}", "small")
        for lq in r.get("literature", []):
            P(f"<b>База знаний:</b> «{E(lq.get('quote',''))}» "
              f"[{E(lq.get('locator') or lq.get('source') or '')}]", "small")
        wp = r.get("world_practice")
        if isinstance(wp, dict) and wp.get("url"):
            P(f"<b>Мировая практика:</b> {E(wp.get('practice',''))} — «{E(wp.get('quote',''))}» "
              f"({E(wp.get('url',''))})", "small")

    def footer(cv, doc):
        cv.setFont(F, 7.5); cv.setFillColor(MUTED)
        cv.drawString(18 * mm, 10 * mm,
                      "Фабрика гипотез · детерминированно · каждое число — из ячейки отчёта")
        cv.drawRightString(A4[0] - 18 * mm, 10 * mm, f"стр. {doc.page}")

    doc = BaseDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                          topMargin=14 * mm, bottomMargin=16 * mm)
    doc.addPageTemplates([PageTemplate(id="m", frames=[
        Frame(18 * mm, 16 * mm, A4[0] - 36 * mm, A4[1] - 30 * mm, id="f")], onPage=footer)])
    doc.build(story)
    return path


# ─────────────────────────── docx (вручную, без зависимостей) ───────────────────────────

_DOCX_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
_DOCX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def _dx(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=False)


def _dp(runs, after=120) -> str:
    """Абзац DOCX. runs — [(text, bold, size_half_pt, color_hex|None)]."""
    xml_runs = ""
    for text, bold, size, color in runs:
        pr = ""
        if bold:
            pr += "<w:b/>"
        if size:
            pr += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
        if color:
            pr += f'<w:color w:val="{color}"/>'
        rpr = f"<w:rPr>{pr}</w:rPr>" if pr else ""
        xml_runs += f'<w:r>{rpr}<w:t xml:space="preserve">{_dx(text)}</w:t></w:r>'
    return f'<w:p><w:pPr><w:spacing w:after="{after}"/></w:pPr>{xml_runs}</w:p>'


def write_docx(data: dict, path: str) -> str:
    meta = data["meta"]
    el = meta["target_element"]
    TEAL, BLUE, MUTED = "0F9C95", "1F6FD0", "6B8593"
    body = [
        _dp([(f"Фабрика гипотез · {meta['fabric']}", True, 38, None)]),
        _dp([(f"бизнес-отчёт · {meta['generated_at']} · источник: {meta['source']} · "
              f"схема: {meta['schema']}", False, 18, MUTED)]),
        _dp([("KPI: ", True, None, BLUE), (meta["kpi"], False, None, None)]),
        _dp([("Извлекаемого металла в хвостах (факт): ", True, None, None),
             (" · ".join(f"{v} т {k}" for k, v in meta["recoverable_tonnes_total"].items()),
              False, None, None)]),
        _dp([(f"Топ-3 гипотезы потенциально адресуют "
              f"{meta['kpi_potential_top3_pct']}% извлекаемых потерь {el} по фабрике. "
              f"Оценка — из данных отчёта (impact); экспериментально не проверено — "
              f"протокол проверки приложен к каждой гипотезе.", False, None, None)]),
    ]
    body += [_dp([(f"⚠ {w}", False, 18, MUTED)]) for w in meta["warnings"]]
    for r in data["hypotheses"]:
        m = r["metrics"]
        body.append(_dp([(f"#{r['rank']} · {r['intervention']} — класс {r['size_class']} "
                          f"({round(m.get('impact', 0)*100)}% потерь {el})",
                          True, 26, TEAL)], after=60))
        for lab, key in (("ЕСЛИ: ", "statement_if"), ("ТО: ", "statement_then"),
                         ("ПОТОМУ ЧТО: ", "statement_because")):
            body.append(_dp([(lab, True, None, BLUE), (r[key], False, None, None)], after=40))
        if r["violates_constraints"]:
            body.append(_dp([("⚠ нарушает ограничение запроса: "
                              + "; ".join(r["violates_constraints"])
                              + " — приоритет занижен, гипотеза не скрыта",
                              False, 18, MUTED)], after=40))
        body.append(_dp([("Эксперимент: ", True, None, None),
                         (r["experiment"], False, None, None)], after=40))
        for s in r.get("roadmap", []):
            body.append(_dp([(f"Этап {s['stage']} — {s['name']}: ", True, 18, TEAL),
                             (f"{s['actions']} · критерий перехода: {s['success']}",
                              False, 18, MUTED)], after=30))
        ev = "; ".join(f"{e.get('label','')} [{e.get('cell','')}]" for e in r["evidence"])
        body.append(_dp([(f"Заземление: {ev} · Источники: {'; '.join(r['sources'])}",
                          False, 18, MUTED)]))
        for lq in r.get("literature", []):
            body.append(_dp([(f"База знаний: «{lq.get('quote','')}» "
                              f"[{lq.get('locator') or lq.get('source') or ''}]",
                              False, 18, MUTED)], after=30))
        wp = r.get("world_practice")
        if isinstance(wp, dict) and wp.get("url"):
            body.append(_dp([(f"Мировая практика: {wp.get('practice','')} — "
                              f"«{wp.get('quote','')}» ({wp.get('url','')})",
                              False, 18, MUTED)]))
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>" + "".join(body) +
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1418"/>'
                "</w:sectPr></w:body></w:document>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _DOCX_CT)
        z.writestr("_rels/.rels", _DOCX_RELS)
        z.writestr("word/document.xml", document)
    return path


# ─────────────────────────── оркестрация ───────────────────────────

def export_all(hyps, profile=None, kpi: str = "", formats="all",
               out_dir: str = "", log=lambda *a: None) -> dict:
    """Выгрузить гипотезы во все запрошенные форматы. Возвращает {формат: путь}."""
    if isinstance(formats, str):
        formats = list(FORMATS) if formats.strip() in ("all", "") else \
            [f.strip() for f in formats.split(",") if f.strip()]
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise ValueError(f"неизвестные форматы: {unknown}; доступны: {', '.join(FORMATS)}")

    data = serialize(hyps, profile=profile, kpi=kpi)
    base = data["meta"]["fabric"] or "гипотезы"
    from factory.config import OUTPUTS_DIR
    out_dir = out_dir or OUTPUTS_DIR
    os.makedirs(out_dir, exist_ok=True)
    p = lambda ext: os.path.join(out_dir, f"{base}_гипотезы.{ext}")

    paths: dict = {}
    if "json" in formats:
        paths["json"] = write_json(data, p("json"))
    if "csv" in formats:
        paths["csv"] = write_csv(data, p("csv"))
    if "tasks" in formats:
        paths["tasks_csv"] = write_tasks_csv(data, os.path.join(out_dir, f"{base}_задачи.csv"))
        paths["tasks_json"] = write_tasks_json(data, os.path.join(out_dir, f"{base}_задачи.json"))
    if "pdf" in formats:
        try:
            paths["pdf"] = write_pdf(data, p("pdf"))
        except RuntimeError as e:          # нет кириллического шрифта — не валим остальное
            log(f"⚠ PDF пропущен: {e}")
    if "docx" in formats:
        paths["docx"] = write_docx(data, p("docx"))
    for k, v in paths.items():
        log(f"  {k:<10} → {v}")
    return paths


def main():
    import argparse

    from factory.pipeline import HypothesisFactory
    from factory.schema import DEFAULT_SCHEMA, load_schema

    ap = argparse.ArgumentParser(
        description="Экспорт гипотез (детерминированно, без LLM): JSON/CSV/задачи/PDF/DOCX")
    ap.add_argument("report", help="путь к Excel-отчёту (Хвосты *.xlsx)")
    ap.add_argument("--kpi", required=True, help="обязателен (как в python -m factory)")
    ap.add_argument("--formats", default="all",
                    help=f"через запятую из {{{','.join(FORMATS)}}} или all")
    ap.add_argument("--schema", default="", help="JSON-схема формата отчёта (опц.)")
    ap.add_argument("--out-dir", default="", help="куда писать (по умолчанию outputs/)")
    args = ap.parse_args()

    if not os.path.exists(args.report):
        ap.error(f"файл отчёта не найден: {args.report}")
    if args.formats.strip() not in ("all", ""):        # fail-fast ДО прогона ядра
        unknown = [f.strip() for f in args.formats.split(",")
                   if f.strip() and f.strip() not in FORMATS]
        if unknown:
            ap.error(f"неизвестные форматы: {', '.join(unknown)}; "
                     f"доступны: {', '.join(FORMATS)} или all")
    schema = load_schema(args.schema) if args.schema else DEFAULT_SCHEMA

    res = HypothesisFactory(args.report, kpi=args.kpi, schema=schema).run()
    print("=" * 74)
    print(f"ЭКСПОРТ · {res['profile'].fabric} · гипотез: {len(res['hypotheses'])}")
    print("=" * 74)
    paths = export_all(res["hypotheses"], profile=res["profile"], kpi=args.kpi,
                       formats=args.formats, out_dir=args.out_dir, log=print)
    if not paths:
        print("ничего не выгружено (проверьте --formats)")


if __name__ == "__main__":
    main()
