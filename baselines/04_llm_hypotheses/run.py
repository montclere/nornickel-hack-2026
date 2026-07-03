#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бейзлайн 4 — LLM-ГЕНЕРАТОР ГИПОТЕЗ (Yandex AI Studio / YandexGPT).

Показывает LLM как ЯЗЫКОВОЙ СЛОЙ над заземлёнными фактами, а не как чёрный ящик:

  1. Собирает GROUNDING-контекст: KPI + ограничения + пронумерованные ФАКТЫ,
     каждый с источником (id + source). Это подаётся модели.
  2. Просит YandexGPT вернуть СТРОГИЙ JSON: список гипотез ЕСЛИ/ТО/ПОТОМУ ЧТО с
     оценками новизны/риска/ценности, протоколом проверки И полем `uses_facts` —
     какие из поданных фактов гипотеза использует.
  3. GROUNDING-ГЕЙТ (критик): гипотеза, которая не ссылается на реальные поданные
     факты, помечается ⚠ (возможная галлюцинация). Модель физически не может
     сослаться на факт, которого мы ей не давали.
  4. Прозрачно ранжирует по value·(1-risk).

Каждый шаг логируется. Домен — во ВНЕШНЕМ `domains/<name>.json` (KPI + факты);
в коде доменных строк нет. Смена домена = другой JSON, код не меняется.

Секреты (YANDEX_API_KEY, YANDEX_FOLDER_ID) — из `.env` (gitignored), не из кода.
Нет ключа/сети → мягкий оффлайн-фейк, бейзлайн всё равно отрабатывает.

Запуск:
    python run.py                        # домен по умолчанию (flotation)
    python run.py domains/alloys.json    # другой домен — тот же движок

Зависимости: только стандартная библиотека Python 3.9+.
"""
from __future__ import annotations

import json
import os
import sys

from llm import YandexLLM, extract_json

_n = [0]
def step(msg):
    _n[0] += 1; print(f"\n[{_n[0]:>2}] ── {msg}")
def sub(msg):
    print(f"        {msg}")

HERE = os.path.dirname(__file__)

SYSTEM = (
    "Ты — научный ассистент R&D. Генерируешь ПРОВЕРЯЕМЫЕ исследовательские гипотезы "
    "СТРОГО на основе поданных фактов. Запрещено выдумывать факты вне списка. "
    "Ответ — ТОЛЬКО валидный JSON-массив, без пояснений."
)

PROMPT_TMPL = """Цель (KPI): {kpi}
Ограничения: {constraints}

ФАКТЫ (используй только их, ссылайся по id):
{facts}

Сгенерируй 3-4 гипотезы. Каждая — объект JSON строго с полями:
"if"   — что сделать (условие),
"then" — ожидаемый результат,
"because" — механизм (обоснование),
"uses_facts" — массив id использованных фактов (например ["f1","f3"]),
"novelty" — число 0..1,
"risk" — число 0..1,
"value" — число 0..1,
"experiment" — краткий протокол проверки.
Верни ТОЛЬКО JSON-массив этих объектов."""


def build_context(dom):
    lines = [f'- [{f["id"]}] {f["text"]} (источник: {f["source"]})' for f in dom["facts"]]
    return "\n".join(lines)


def offline_stub(dom):
    """Оффлайн-фейк, если нет ключа/сети — чтобы бейзлайн всегда отрабатывал."""
    f = dom["facts"]
    return [{
        "if": "использовать первый факт как рычаг",
        "then": "улучшить целевой KPI",
        "because": f[0]["text"],
        "uses_facts": [f[0]["id"]],
        "novelty": 0.5, "risk": 0.4, "value": 0.6,
        "experiment": "лабораторная проверка (оффлайн-заглушка)",
    }]


def grounding_gate(hyps, valid_ids):
    """Критик: пометить гипотезы, не заземлённые на реальные поданные факты."""
    for h in hyps:
        used = [i for i in h.get("uses_facts", []) if i in valid_ids]
        h["_grounded"] = bool(used)
        h["_used_valid"] = used
        h["_used_invalid"] = [i for i in h.get("uses_facts", []) if i not in valid_ids]
    return hyps


def run_domain(path):
    dom = json.load(open(path, encoding="utf-8"))
    print("\n" + "=" * 78)
    print(f"ДОМЕН: {dom['name']}   (конфиг: {os.path.basename(path)})")
    print("=" * 78)

    step(f"Собираю GROUNDING-контекст: KPI + {len(dom['facts'])} фактов с источниками")
    sub(f"KPI: {dom['kpi']}")
    sub(f"ограничения: {dom['constraints']}")
    context = build_context(dom)
    for line in context.splitlines():
        sub(line)

    llm = YandexLLM(model="yandexgpt/latest", temperature=0.3)
    step(f"Зову YandexGPT (Yandex AI Studio), ключ из .env: "
         f"{'есть' if llm.ready else 'НЕТ → оффлайн-фейк'}")
    if llm.ready:
        user = PROMPT_TMPL.format(kpi=dom["kpi"], constraints=dom["constraints"], facts=context)
        try:
            raw = llm.complete(SYSTEM, user)
            sub(f"получен ответ: {len(raw)} символов")
            hyps = extract_json(raw)
            if not isinstance(hyps, list):
                raise ValueError("модель вернула не JSON-массив")
        except Exception as e:  # noqa: BLE001
            sub(f"⚠ ошибка LLM ({e}) → оффлайн-фейк")
            hyps = offline_stub(dom)
    else:
        hyps = offline_stub(dom)

    step("GROUNDING-ГЕЙТ (критик): проверяю ссылки гипотез на реальные факты")
    valid_ids = {f["id"] for f in dom["facts"]}
    hyps = grounding_gate(hyps, valid_ids)
    ok = sum(h["_grounded"] for h in hyps)
    sub(f"заземлено {ok}/{len(hyps)} гипотез (ссылаются на поданные факты)")

    step("Ранжирую (value·(1-risk)) и печатаю карточки")
    for h in hyps:
        h["_score"] = round(float(h.get("value", 0)) * (1 - float(h.get("risk", 0))), 3)
    hyps.sort(key=lambda h: -h["_score"])
    for i, h in enumerate(hyps, 1):
        flag = "" if h["_grounded"] else "  ⚠ НЕ ЗАЗЕМЛЕНА (возможная галлюцинация)"
        print(f"\n   #{i}  score={h['_score']}  "
              f"novelty={h.get('novelty')} risk={h.get('risk')} value={h.get('value')}{flag}")
        print(f"       ЕСЛИ:  {h.get('if')}")
        print(f"       ТО:    {h.get('then')}")
        print(f"       П.Ч.:  {h.get('because')}")
        print(f"       эксперимент: {h.get('experiment')}")
        cited = ", ".join(f"[{i}] {facts_by_id(dom, i)}" for i in h["_used_valid"]) or "—"
        print(f"       заземление на факты: {cited}")
        if h["_used_invalid"]:
            print(f"       ⚠ ссылки на несуществующие факты: {h['_used_invalid']}")


def facts_by_id(dom, fid):
    for f in dom["facts"]:
        if f["id"] == fid:
            return f["source"]
    return "?"


def main():
    args = sys.argv[1:] or [os.path.join(HERE, "domains", "flotation.json")]
    for a in args:
        run_domain(a if os.path.exists(a) else os.path.join(HERE, a))
    print("\n" + "=" * 78)
    print("LLM — языковой слой над заземлёнными фактами. Grounding-гейт ловит выдумки.")
    print("Домен во внешнем JSON; секреты в .env. Смена домена = другой JSON.")
    print("=" * 78)


if __name__ == "__main__":
    main()
