#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бейзлайн 3 — АНТИ-ГРАФ ПРОВАЛОВ (память о граблях). УНИВЕРСАЛЬНЫЙ ДВИЖОК.

В коде — только домен-независимая логика сверки гипотезы с «кладбищем» провалов:
    совпало + причина в силе   → 🔴 красный флаг
    совпало + свежий факт снял → 🟢 реанимация
    нет пересечения            → ⚪ чисто

Весь домен — во ВНЕШНЕМ конфиге `domains/<name>.json`:
    graveyard (провалы), fresh_facts (снимающие причину), incoming (гипотезы),
    lift_families (какие подстроки причин вообще снимаемы).
Смена домена = другой JSON, КОД НЕ МЕНЯЕТСЯ.

Идея кейса: снижение зависимости от субъективного опыта — система помнит грабли за
годы, даже если сотрудник забыл; и подсвечивает УСТАРЕВШИЕ закрытия.

Запуск:
    python run.py                       # домен по умолчанию (flotation)
    python run.py domains/alloys.json   # другой домен — тот же движок

Зависимости: только стандартная библиотека Python 3.9+.
"""
from __future__ import annotations

import json
import os
import sys

_n = [0]
def step(msg):
    _n[0] += 1; print(f"\n[{_n[0]:>2}] ── {msg}")
def sub(msg):
    print(f"        {msg}")

HERE = os.path.dirname(__file__)


# ─────────────────────────────────────────────────────────────────────────────
# Ядро: сверка гипотезы с кладбищем. Ничего доменного — только данные из конфига.
# ─────────────────────────────────────────────────────────────────────────────
def check(hyp, graveyard, fresh_facts, lift_families, generic_terms=()):
    h = hyp.lower()
    for fail in graveyard:
        subj = fail["subject"].lower()
        # различающие слова субъекта: длиной ≥4 и НЕ родовые действия
        # («добавка», «легирование» и т.п.) — иначе «добавка бора» ложно совпадёт
        # с «добавка ниобия». Родовые термины задаёт конфиг домена.
        keys = [w for w in subj.split() if len(w) >= 4 and w not in generic_terms]
        if not keys or not any(w in h for w in keys):
            continue
        reason = fail["closure_reason"].lower()
        needle = next((k for k in lift_families if k in reason), None)
        fresh = None
        if needle:
            fresh = next((f for f in fresh_facts
                          if fail["subject"].lower() in f["about"].lower()
                          and f["lifts"] == needle and f["year"] > fail["year"]), None)
        return ("🟢 РЕАНИМАЦИЯ", fail, fresh) if fresh else ("🔴 КРАСНЫЙ ФЛАГ", fail, None)
    return "⚪ чисто", None, None


# ─────────────────────────────────────────────────────────────────────────────
def run_domain(path):
    dom = json.load(open(path, encoding="utf-8"))
    gy, ff = dom["graveyard"], dom["fresh_facts"]
    lift = dom.get("lift_families", [])
    generic = set(dom.get("generic_terms", []))
    print("\n" + "=" * 78)
    print(f"ДОМЕН: {dom['name']}   (конфиг: {os.path.basename(path)})")
    print("=" * 78)

    step(f"Кладбище: {len(gy)} задокументированных провалов")
    for f in gy:
        sub(f"✗ «{f['subject']}» закрыт {f['year']}: {f['closure_reason']} [{f['report']}]")

    step(f"Свежие факты, способные снять причину: {len(ff)}")
    for f in ff:
        sub(f"↑ {f['year']}: {f['quote']} [{f['source']}]")

    step(f"Проверяю {len(dom['incoming'])} входящих гипотез")
    red = green = clean = 0
    for hyp in dom["incoming"]:
        status, fail, fresh = check(hyp, gy, ff, lift, generic)
        print(f"\n   {status}  {hyp}")
        if fail and not fresh:
            red += 1
            sub(f"уже пробовали: «{fail['subject']}» → {fail['year']} "
                f"({fail['closure_reason']}) [{fail['report']}]")
            sub("рекомендация: не повторять вслепую — укажите, чем отличается")
        elif fresh:
            green += 1
            sub(f"провал {fail['year']} ({fail['closure_reason']}) [{fail['report']}], "
                f"НО факт {fresh['year']} снимает причину:")
            sub(f"  «{fresh['quote']}» [{fresh['source']}]")
            sub("рекомендация: кандидат на возврат — причина закрытия устарела")
        else:
            clean += 1
            sub("пересечений с кладбищем нет")

    step("Итог")
    sub(f"🔴 красных: {red}   🟢 реанимаций: {green}   ⚪ чистых: {clean}")


def main():
    args = sys.argv[1:] or [os.path.join(HERE, "domains", "flotation.json")]
    for a in args:
        run_domain(a if os.path.exists(a) else os.path.join(HERE, a))
    print("\n" + "=" * 78)
    print("Один движок, разные JSON-домены (флотация / сплавы). В коде — ноль")
    print("доменных строк; кладбище и факты внешние. В проде их извлекает пайплайн")
    print("из реальных отчётов (маркеры «не дало эффекта»/«дорого») и агент-поисковик.")
    print("=" * 78)


if __name__ == "__main__":
    main()
