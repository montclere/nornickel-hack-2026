#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Бейзлайн 5 — ИЗВЛЕЧЕНИЕ ЗНАНИЙ ИЗ ДОКУМЕНТА (Yandex AI Studio).

Отвечает на вопрос «откуда берётся конфиг»: он НЕ пишется руками, а ПОРОЖДАЕТСЯ из
базы знаний. Это недостающий «кор»-шаг фабрики: документ → структурированное знание.

Что делает (по шагам):
  1. Читает реальный документ (docx/txt) — базу знаний домена.
  2. LLM (YandexGPT) извлекает СТРУКТУРИРОВАННЫЕ факты в JSON, КАЖДЫЙ с полем
     `quote` — дословной цитатой из текста.
  3. ЦИТАТНЫЙ ГЕЙТ (анти-галлюцинация): факт принимается ТОЛЬКО если его `quote`
     реально встречается в исходном тексте (нормализованное вхождение). Выдумки
     отсекаются автоматически.
  4. Сохраняет прошедшие факты в `knowledge.json` — это и есть тот самый конфиг,
     который потом кормит генерацию (бейзлайны 04/01). Сгенерирован, не подтасован.

Так «смена домена = другой JSON» превращается в «загрузи документы → получи JSON».

Секреты — из общего `baselines/.env` (gitignored). Нет ключа/сети → оффлайн-фейк.

Запуск:
    python run.py                                  # документ по умолчанию
    python run.py "domains/<любой>.docx"           # свой документ
    python run.py --out knowledge.json             # куда сохранить

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

from llm import YandexLLM, extract_json

_n = [0]
def step(msg):
    _n[0] += 1; print(f"\n[{_n[0]:>2}] ── {msg}")
def sub(msg):
    print(f"        {msg}")

HERE = os.path.dirname(__file__)

SYSTEM = (
    "Ты — инженер знаний. Извлекаешь из научно-технического текста проверяемые ФАКТЫ-"
    "связи (что на что влияет, что чем извлекается/характеризуется). Ничего не выдумывай. "
    "Ответ — ТОЛЬКО валидный JSON-массив."
)

PROMPT_TMPL = """Ниже текст доменного документа. Извлеки 5-8 фактов.
Каждый факт — объект JSON строго с полями:
"fact"  — краткая формулировка связи/правила (1 предложение),
"quote" — ДОСЛОВНАЯ подстрока из текста ниже, подтверждающая факт (скопируй буквально),
"entities" — массив ключевых сущностей факта.
Верни ТОЛЬКО JSON-массив.

ТЕКСТ:
\"\"\"
{doc}
\"\"\""""


def read_docx_text(path):
    z = zipfile.ZipFile(path)
    xml = z.read("word/document.xml").decode("utf-8", "ignore")
    return html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml)))


def read_text(path):
    if path.lower().endswith(".docx"):
        return read_docx_text(path)
    return open(path, encoding="utf-8", errors="ignore").read()


def normalize(s: str) -> str:
    """Нормализация для цитатного гейта: схлопнуть пробелы, привести регистр."""
    return re.sub(r"\s+", " ", s or "").strip().lower()


def citation_gate(facts, source_text, source_name):
    """Оставить факты, чья quote реально есть в тексте (защита от галлюцинаций)."""
    norm_src = normalize(source_text)
    kept, dropped = [], []
    for f in facts:
        q = normalize(f.get("quote", ""))
        if q and len(q) >= 8 and q in norm_src:
            f["source"] = source_name
            kept.append(f)
        else:
            dropped.append(f)
    return kept, dropped


def offline_stub(source_name):
    return [{
        "fact": "Потенциально извлекаемые минералы никеля — раскрытый и закрытый пентландит и миллерит.",
        "quote": "для элемента 28 потенциально извлекаемыми минералами являются: раскрытый и закрытый pnt, миллерит",
        "entities": ["никель", "пентландит", "миллерит"], "source": source_name,
    }]


def run_doc(path, out_path):
    name = os.path.basename(path)
    print("\n" + "=" * 78)
    print(f"ДОКУМЕНТ: {name}")
    print("=" * 78)

    step(f"Читаю документ (docx/txt): {name}")
    text = read_text(path)
    sub(f"символов: {len(text)}")
    sub("превью: " + normalize(text)[:160] + "…")

    llm = YandexLLM(model="yandexgpt/latest", temperature=0.2)
    step(f"Извлекаю факты через YandexGPT (ключ из .env: "
         f"{'есть' if llm.ready else 'НЕТ → оффлайн-фейк'})")
    if llm.ready:
        try:
            raw = llm.complete(SYSTEM, PROMPT_TMPL.format(doc=text[:6000]))
            facts = extract_json(raw)
            if not isinstance(facts, list):
                raise ValueError("не JSON-массив")
            sub(f"модель вернула фактов: {len(facts)}")
        except Exception as e:  # noqa: BLE001
            sub(f"⚠ ошибка LLM ({e}) → оффлайн-фейк")
            facts = offline_stub(name)
    else:
        facts = offline_stub(name)

    step("ЦИТАТНЫЙ ГЕЙТ: оставляю только факты с дословной цитатой из текста")
    kept, dropped = citation_gate(facts, text, name)
    sub(f"принято {len(kept)}, отброшено (нет дословной цитаты) {len(dropped)}")
    for f in dropped:
        sub(f"  ✗ отброшен (галлюцинация?): {f.get('fact','')[:70]}")

    step("Извлечённое знание (заземлено до цитаты):")
    for i, f in enumerate(kept, 1):
        print(f"\n   [{i}] {f['fact']}")
        print(f"       сущности: {', '.join(f.get('entities', []))}")
        print(f"       ↳ цитата [{f['source']}]: «{f['quote'][:110]}»")

    step(f"Сохраняю как конфиг знаний → {os.path.basename(out_path)}")
    # формат совместим с бейзлайном 04 (facts с id+source)
    knowledge = {
        "name": f"Авто-извлечение из «{name}»",
        "source_document": name,
        "facts": [{"id": f"k{i+1}", "text": f["fact"], "source": f["source"],
                   "quote": f["quote"], "entities": f.get("entities", [])}
                  for i, f in enumerate(kept)],
    }
    json.dump(knowledge, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    sub(f"записано фактов: {len(knowledge['facts'])} → передаётся в генерацию (бейзлайн 04)")


def main():
    args = sys.argv[1:]
    out = os.path.join(HERE, "knowledge.json")
    if "--out" in args:
        i = args.index("--out"); out = args[i + 1]; del args[i:i + 2]
    if args:
        docs = [a if os.path.exists(a) else os.path.join(HERE, a) for a in args]
    else:
        docs = sorted(glob.glob(os.path.join(HERE, "domains", "*.docx")))
    if not docs:
        print("Нет документов. Положите .docx/.txt в domains/"); return
    for d in docs:
        run_doc(d, out)
    print("\n" + "=" * 78)
    print("Конфиг знаний СГЕНЕРИРОВАН из документа (не написан руками). Цитатный гейт")
    print("гарантирует заземление. Дальше knowledge.json кормит генерацию (04/01).")
    print("=" * 78)


if __name__ == "__main__":
    main()
