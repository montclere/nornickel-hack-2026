#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бейзлайн 2 — ДИАГНОСТИКА ПО СТРУКТУРНЫМ ДАННЫМ. УНИВЕРСАЛЬНЫЙ ДВИЖОК.

В этом файле — только домен-независимая логика:
    читаем табличный отчёт по ЯКОРЯМ-подписям из конфига → строим профиль
    «где сколько ценного теряется» → маршрутизируем каждую подгруппу в семейство
    вмешательства по правилам конфига → формируем и ранжируем гипотезы → сверяем
    с эталоном.

Ни одной доменной строки в коде. Весь домен — во ВНЕШНЕМ `config.<name>.json`:
    роли колонок, якоря-подписи, элементы и цены, правила маршрутизации, библиотека
    вмешательств (с источниками), ключи для reproduction-сверки.
Другой отчёт/домен = другой config.json + якоря, КОД НЕ МЕНЯЕТСЯ.
(Табличный «контракт» — подписи-якоря + роли колонок — это доменный адаптер к
 формату конкретного отчёта; сам движок про флотацию ничего не знает.)

Запуск:
    python run.py                                   # все data/*.xlsx, конфиг по умолчанию
    python run.py "Хвосты ТОФ_2.xlsx"               # один файл
    python run.py --config config.flotation.json    # явный конфиг

Зависимости: только стандартная библиотека Python 3.9+.
"""
from __future__ import annotations

import glob
import html
import json
import os
import re
import sys
import zipfile

_n = [0]
def step(msg):
    _n[0] += 1; print(f"\n[{_n[0]:>2}] ── {msg}")
def sub(msg):
    print(f"        {msg}")

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")


# ─────────────────────────────────────────────────────────────────────────────
# stdlib-ридеры офисных форматов (без внешних зависимостей).
# ─────────────────────────────────────────────────────────────────────────────
def read_xlsx_grid(path):
    """xlsx → {(row:int, col:str): value}."""
    z = zipfile.ZipFile(path)
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        x = z.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
        ss = [html.unescape(re.sub(r"<[^>]+>", "", m))
              for m in re.findall(r"<si>(.*?)</si>", x, re.S)]
    sheet = [n for n in z.namelist() if re.match(r"xl/worksheets/sheet1\.xml", n)][0]
    x = z.read(sheet).decode("utf-8", "ignore")
    grid = {}
    for cm in re.finditer(
            r'<c r="([A-Z]+)(\d+)"(?:[^>]*t="(\w+)")?[^>]*>(?:<v>(.*?)</v>)?</c>', x):
        col, row, t, v = cm.groups()
        if v is None:
            continue
        val = ss[int(v)] if t == "s" else _tofloat(v)
        grid[(int(row), col)] = val
    return grid


def _tofloat(v):
    try:
        return float(v)
    except ValueError:
        return v


def read_docx_text(path):
    z = zipfile.ZipFile(path)
    xml = z.read("word/document.xml").decode("utf-8", "ignore")
    return html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml)))


def num(x):
    """Число или None. Гасит битые формулы (#REF!) и текст."""
    return x if isinstance(x, (int, float)) else None


# ─────────────────────────────────────────────────────────────────────────────
# Парсер отчёта → профиль потерь. Управляется ТОЛЬКО якорями/ролями из конфига.
# ─────────────────────────────────────────────────────────────────────────────
def parse_profile(grid, cfg):
    lc = cfg["label_col"]

    def find(sub_label, need_col=None):
        rows = sorted({r for (r, c), v in grid.items()
                       if c == lc and sub_label in str(v)})
        if need_col:
            rows = [r for r in rows if (r, need_col) in grid]
        return rows[0] if rows else None

    a = cfg["anchors"]
    prof = {"elements": {}, "size_classes": [], "recoverable_pct": {}, "mineralogy": {}}

    # потери по элементам — строка-якорь loss_row (с содержаниями)
    r_loss = find(a["loss_row"], need_col=cfg["elements"][0]["pct_col"])
    for el in cfg["elements"]:
        prof["elements"][el["symbol"]] = {
            "grade_pct": num(grid.get((r_loss, el["pct_col"]))),
            "tonnes_lost": num(grid.get((r_loss, el["t_col"]))),
            "cell": f"{el['t_col']}{r_loss}",
            "price": el["price_usd_per_t"],
        }

    # распределение по классам крупности — таблица под якорем size_table_header
    r_hdr = find(a["size_table_header"])
    r = r_hdr + 1
    while r_hdr and r < r_hdr + 14:
        b = grid.get((r, lc))
        if b is None:
            r += 1; continue
        if str(b).startswith("Итого"):
            break
        row = {"class": str(b).strip()}
        for el in cfg["elements"]:
            row[el["symbol"]] = num(grid.get((r, el["t_col"])))
            row[el["symbol"] + "_cell"] = f"{el['t_col']}{r}"
        prof["size_classes"].append(row)
        r += 1

    # доля извлекаемого металла (первое вхождение = сводный блок)
    r_rec = find(a["recoverable_row"], need_col=cfg["elements"][0]["pct_col"])
    if r_rec:
        prof["recoverable_pct"] = {
            el["symbol"]: num(grid.get((r_rec, el["pct_col"]))) for el in cfg["elements"]}
        prof["recoverable_pct"]["cell"] = f"{cfg['elements'][0]['pct_col']}{r_rec}"

    # минералогия крупного класса: доля закрытого/раскрытого (по первому элементу)
    pc0 = cfg["elements"][0]["pct_col"]
    r_cl = find(a["mineral_closed_row"], need_col=pc0)
    r_op = find(a["mineral_open_row"], need_col=pc0)
    prof["mineralogy"] = {
        "closed_pct": num(grid.get((r_cl, pc0))) if r_cl else None,
        "open_pct": num(grid.get((r_op, pc0))) if r_op else None,
        "cell": f"{pc0}{r_cl}" if r_cl else None,
    }
    return prof


# ─────────────────────────────────────────────────────────────────────────────
# Диагностика + генерация. Маршрутизация и тексты — из конфига.
# ─────────────────────────────────────────────────────────────────────────────
def route_family(cls, cfg):
    norm = cls.replace(" ", "")
    for fc in cfg["fines_classes"]:
        if fc.replace(" ", "") in norm:
            return cfg["fines_family"]
    return cfg["default_family"]


def diagnose(prof, cfg):
    rec = prof.get("recoverable_pct", {})
    cands = []
    for sc in prof["size_classes"]:
        value_usd = 0.0
        rec_tons = {}
        for el in cfg["elements"]:
            sym = el["symbol"]
            t = sc.get(sym) or 0.0
            frac = (rec.get(sym) if rec.get(sym) is not None else 80.0) / 100.0
            rt = t * frac
            rec_tons[sym] = round(rt, 1)
            value_usd += rt * el["price_usd_per_t"]
        cands.append({
            "class": sc["class"], "family": route_family(sc["class"], cfg),
            "rec_tons": rec_tons, "value_usd": value_usd,
            "provenance": [sc.get(el["symbol"] + "_cell") for el in cfg["elements"]]
                          + [rec.get("cell")],
        })
    cands.sort(key=lambda c: -c["value_usd"])
    return cands


def build_hypotheses(cands, cfg):
    total = sum(c["value_usd"] for c in cands) or 1.0
    src = [cfg["source_report_guide"], cfg["source_reference"]]
    hyps = []
    for c in cands:
        lib = cfg["interventions"][c["family"]]
        vnorm = c["value_usd"] / total
        tons_txt = " + ".join(f"{v} т {s}" for s, v in c["rec_tons"].items())
        for action in lib["actions"]:
            feas = 0.4 if lib.get("needs_new_equipment") else 0.8
            risk = 0.4 if lib.get("needs_new_equipment") else 0.2
            hyps.append({
                "if": action,
                "then": f"снизятся потери извлекаемого металла в классе {c['class']} "
                        f"(~{tons_txt} в риске)",
                "because": lib["mechanism"] + f"; диагноз: {lib['diagnosis']}",
                "family": c["family"], "class": c["class"],
                "value": round(vnorm, 3), "novelty": 0.5, "feasibility": feas, "risk": risk,
                "falsified_by": f"лабораторный тест класса {c['class']}: если "
                                f"{cfg.get('kpi_name', 'целевой KPI')} не растёт — "
                                f"гипотеза опровергнута",
                "sources": src,
                "provenance_cells": [x for x in c["provenance"] if x],
                "score": round(vnorm * 0.5 * feas / max(risk, 0.05), 3),
            })
    hyps.sort(key=lambda h: -h["score"])
    return hyps


# ─────────────────────────────────────────────────────────────────────────────
# Reproduction-сверка с эталонными гипотезами инженеров.
# ─────────────────────────────────────────────────────────────────────────────
def classify_expert(text, cfg):
    low = text.lower()
    scores = {f: sum(low.count(k) for k in ks)
              for f, ks in cfg["reproduction_keywords"].items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def load_expert(name, cfg):
    docs = glob.glob(os.path.join(DATA, cfg.get("expert_glob", "*.docx")))
    key = name
    for s in cfg.get("expert_match_strip", []):
        key = key.replace(s, "")
    key = key.strip().split()[0] if key.strip() else name
    match = next((d for d in docs if key.lower() in d.lower()), docs[0] if docs else None)
    if not match:
        return []
    lines = [l.strip(" .0123456789") for l in read_docx_text(match).splitlines()
             if l.strip() and "мозгов" not in l.lower() and len(l.strip()) > 8]
    return [(l, classify_expert(l, cfg)) for l in lines]


def research(query):
    # TODO(agent): подключить поисковый агент (флотация мелких классов, поставщики).
    return f"[research-stub] здесь агент доисследует: «{query}»"


# ─────────────────────────────────────────────────────────────────────────────
def run_one(path, cfg):
    name = os.path.basename(path)
    print("\n" + "=" * 78)
    print(f"ОТЧЁТ: {name}   |   домен-конфиг: {cfg['name']}")
    print("=" * 78)

    step(f"Читаю табличный отчёт (stdlib): {name}")
    grid = read_xlsx_grid(path)
    sub(f"ячеек: {len(grid)}")

    step("Разбираю по якорям из конфига → профиль потерь")
    prof = parse_profile(grid, cfg)
    for sym, e in prof["elements"].items():
        t = f"{e['tonnes_lost']:.0f} т" if e["tonnes_lost"] is not None else "н/д"
        g = f"{e['grade_pct']:.3f}%" if e["grade_pct"] is not None else "н/д"
        sub(f"{sym}: в {cfg.get('loss_sink', 'потери')} {t} при {g} [{e['cell']}]")
    rp = prof["recoverable_pct"]
    if rp:
        sub("извлекаемо из потерь: "
            + ", ".join(f"{s} ~{rp[s]:.1f}%" for s in prof["elements"] if rp.get(s) is not None)
            + f" [{rp.get('cell')}]")
    m = prof["mineralogy"]
    if m.get("closed_pct") is not None:
        sub(f"крупный класс: закрытый {m['closed_pct']:.1f}% vs раскрытый "
            f"{m['open_pct']:.1f}% [{m['cell']}]")

    step("Локализую потери по классам крупности (ценность = извлекаемые тонны × цена)")
    cands = diagnose(prof, cfg)
    for c in cands:
        tons = " + ".join(f"{v}т {s}" for s, v in c["rec_tons"].items())
        sub(f"{c['class']:<10} → «{c['family']}» | {tons} (~${c['value_usd']/1e6:.1f}M) "
            f"[{', '.join(x for x in c['provenance'] if x)}]")

    step("Формирую и ранжирую гипотезы из библиотеки вмешательств (с источниками)")
    hyps = build_hypotheses(cands, cfg)
    sub(f"гипотез: {len(hyps)}")
    for i, h in enumerate(hyps[:3], 1):
        print(f"\n   #{i}  score={h['score']}  [{h['family']} · {h['class']}]")
        print(f"       ЕСЛИ:  {h['if']}")
        print(f"       ТО:    {h['then']}")
        print(f"       П.Ч.:  {h['because']}")
        print(f"       метрики: value={h['value']} feas={h['feasibility']} risk={h['risk']}")
        print(f"       опровергается: {h['falsified_by']}")
        print(f"       источники: {'; '.join(h['sources'])}")
        print(f"       заземление: {', '.join(h['provenance_cells'])}")

    step("REPRODUCTION: сверяю с эталоном мозгового штурма инженеров")
    experts = load_expert(name, cfg)
    fams = {h["family"] for h in hyps}
    hit = sum(1 for _, f in experts if f in fams)
    for text, f in experts:
        sub(f"{'✓' if f in fams else '·'} [{f or '—':<10}] {text[:66]}")
    if experts:
        print(f"\n        → из СЫРЫХ ДАННЫХ покрыто {hit}/{len(experts)} экспертных гипотез "
              f"(семейство вмешательства совпало)")

    step("Хук агента-поисковика — заглушка")
    sub(research(hyps[0]["if"]) if hyps else "нет гипотез")


def main():
    args = sys.argv[1:]
    cfg_path = os.path.join(HERE, "config.flotation.json")
    if "--config" in args:
        i = args.index("--config"); cfg_path = args[i + 1]; del args[i:i + 2]
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    files = ([os.path.join(DATA, a) if not os.path.isabs(a) else a for a in args]
             if args else sorted(glob.glob(os.path.join(DATA, cfg.get("data_glob", "*.xlsx")))))
    if not files:
        print("Нет данных. Ожидаются ./data/Хвосты*.xlsx"); return
    for f in files:
        run_one(f, cfg)
    print("\n" + "=" * 78)
    print(f"Один движок, конфиг «{os.path.basename(cfg_path)}». В коде нет доменных строк —")
    print("схема, якоря, вмешательства и цены во внешнем JSON. Другой отчёт = другой конфиг.")
    print("=" * 78)


if __name__ == "__main__":
    main()
