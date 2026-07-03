# -*- coding: utf-8 -*-
"""Извлечение сущностей и связей из ТЕКСТА через LLM + ЦИТАТНЫЙ ГЕЙТ + кэш.

Это слой понимания неструктурированных данных (статьи/патенты/отчёты). LLM читает
фрагмент и возвращает связи (subject —тип→ object) с дословной цитатой. Связь
принимается ТОЛЬКО если цитата реально есть во фрагменте → выдумки отсекаются.
После кэширования весь downstream детерминирован (тот же кэш → тот же граф).

Структура НЕ хардкодится: работает на любом тексте; тип связи выбирается из закрытого
словаря, поэтому знак влияния детерминирован (критик знаков не нужен).
"""
from __future__ import annotations

import json
import os
import re

from factory.llm import Yandex, extract_json

# закрытый словарь типов связи → знак (LLM только ВЫБИРАЕТ тип, знак ставим мы)
RELATION_VOCAB = {"повышает": +1, "снижает": -1, "не_влияет": 0, "связан": 0}
_SYN = {"увеличивает": "повышает", "усиливает": "повышает", "улучшает": "повышает",
        "уменьшает": "снижает", "ослабляет": "снижает", "ухудшает": "снижает",
        "подавляет": "снижает", "не влияет": "не_влияет", "связано": "связан",
        "характеризует": "связан"}

SYSTEM = ("Ты — инженер знаний (материаловедение/обогащение). Извлекаешь из текста "
          "проверяемые связи между сущностями (материалы, параметры, свойства, процессы), "
          "КЛАССИФИЦИРУЯ тип. Ничего не выдумываешь. Ответ — ТОЛЬКО JSON-массив.")
PROMPT = """Из фрагмента извлеки связи (до 5). Каждая — объект строго с полями:
"subject" — сущность-причина, "relation" — РОВНО ОДИН тип из [{rel}],
"object" — сущность-следствие, "quote" — ДОСЛОВНАЯ подстрока из фрагмента.
Не придумывай типы связи. Бери только явно написанные связи. ТОЛЬКО JSON-массив.

ФРАГМЕНТ:
\"\"\"
{chunk}
\"\"\""""


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _canon_rel(rel):
    r = _norm(rel).replace(" ", "_")
    return r if r in RELATION_VOCAB else _SYN.get(_norm(rel))


def _tokens(s):
    return set(re.findall(r"[а-яёa-z]{4,}", (s or "").lower()))


def _select(chunks, max_chunks, query):
    prose = [c for c in chunks if c.kind == "prose" and len(c.text) >= 200
             and sum(ch.isalpha() for ch in c.text) / max(len(c.text), 1) >= 0.55]
    if query:
        qt = _tokens(query)
        prose.sort(key=lambda c: -len(_tokens(c.text) & qt))
    else:
        prose.sort(key=lambda c: -len(c.text))
    return prose[:max_chunks]


def extract_relations(chunks, llm=None, max_chunks=12, query=None,
                      cache_path=None, log=lambda *a: None):
    """chunks → список связей с провенансом. Кэш делает downstream детерминированным."""
    if cache_path and os.path.exists(cache_path):
        cached = json.load(open(cache_path, encoding="utf-8"))
        if cached:                       # пустой кэш не считаем валидным → переизвлекаем
            log(f"кэш графа: {os.path.basename(cache_path)} ({len(cached)} связей)")
            return cached
        log("кэш пуст — переизвлекаю")

    llm = llm or Yandex(model="yandexgpt/latest", temperature=0.0)
    if not llm.ready:
        raise RuntimeError("нет ключа Yandex (.env) — извлечение из текста требует LLM")

    rels, stats = [], {"raw": 0, "kept": 0, "dropped": 0}
    for i, c in enumerate(_select(chunks, max_chunks, query), 1):
        try:
            raw = llm.complete(SYSTEM, PROMPT.format(chunk=c.text[:3500],
                                                     rel=", ".join(RELATION_VOCAB)))
            triples = extract_json(raw) or []
        except Exception as e:  # noqa: BLE001
            log(f"  фрагмент {i}: ошибка LLM ({e})"); continue
        if not isinstance(triples, list):
            continue
        nt = _norm(c.text); kept = 0
        for t in triples:
            stats["raw"] += 1
            q = _norm(t.get("quote", "")); rel = _canon_rel(t.get("relation", ""))
            subj, obj = t.get("subject", ""), t.get("object", "")
            if not (subj and obj) or rel is None or len(q) < 8 or q not in nt:
                stats["dropped"] += 1; continue
            rels.append({"subject": subj.strip(), "relation": rel,
                         "sign": RELATION_VOCAB[rel], "object": obj.strip(),
                         "quote": t.get("quote", "").strip(),
                         "source": c.source, "locator": c.locator, "meta": c.meta})
            kept += 1
        stats["kept"] += kept
        log(f"  {i}/{max_chunks} [{c.locator}]: +{kept} связей")
    log(f"извлечено {stats['kept']} связей (сырых {stats['raw']}, "
        f"отброшено гейтом {stats['dropped']})")
    if cache_path and rels:              # пустой результат не кэшируем
        json.dump(rels, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rels
