# -*- coding: utf-8 -*-
"""Авто-извлечение графа знаний из фрагментов через LLM + ЦИТАТНЫЙ ГЕЙТ.

Никаких фактов руками: LLM читает фрагмент и возвращает триплеты
(subject —relation[sign]→ object) с дословной цитатой. Триплет принимается ТОЛЬКО
если цитата реально есть во фрагменте → галлюцинации отсекаются автоматически.
"""
from __future__ import annotations

import re

from common.llm import extract_json

# ЗАКРЫТЫЙ словарь типов связи → знак. LLM НЕ придумывает связь и НЕ ставит знак,
# а только ВЫБИРАЕТ тип из этого списка; знак подставляем мы детерминированно.
# Поэтому отдельный «критик знаков» не нужен — семантика знака фиксирована.
RELATION_VOCAB = {
    "повышает": +1,     # увеличивает / усиливает / улучшает целевое свойство
    "снижает": -1,      # уменьшает / ослабляет / ухудшает
    "не_влияет": 0,     # явно указано отсутствие влияния
    "связан": 0,        # ассоциация / характеризует, без направления эффекта
}
RELATION_LIST = ", ".join(RELATION_VOCAB)

SYSTEM = (
    "Ты — инженер знаний в металлургии/обогащении. Извлекаешь из текста проверяемые "
    "связи, КЛАССИФИЦИРУЯ каждую в один из заданных типов. Ничего не выдумываешь. "
    "Ответ — ТОЛЬКО JSON-массив."
)

PROMPT = """Из фрагмента извлеки связи между сущностями (до 5).
Каждая — объект строго с полями:
"subject" — что влияет (сущность),
"relation" — РОВНО ОДИН тип из списка: [{relations}],
"object" — на что влияет (сущность),
"quote" — ДОСЛОВНАЯ подстрока из фрагмента (скопируй буквально).
Не придумывай свои типы связи — выбирай только из списка. Бери только явно
написанные в тексте связи. Верни ТОЛЬКО JSON-массив.

ФРАГМЕНТ:
\"\"\"
{chunk}
\"\"\""""


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


# синонимы → канонический тип из словаря (на случай, если LLM слегка отклонится)
_REL_SYNONYMS = {
    "повышает": "повышает", "увеличивает": "повышает", "усиливает": "повышает",
    "улучшает": "повышает", "активирует": "повышает",
    "снижает": "снижает", "уменьшает": "снижает", "ослабляет": "снижает",
    "ухудшает": "снижает", "подавляет": "снижает", "деактивирует": "снижает",
    "не_влияет": "не_влияет", "не влияет": "не_влияет",
    "связан": "связан", "связано": "связан", "характеризует": "связан",
}


def _canon_relation(rel):
    """Привести тип связи к канону из RELATION_VOCAB; вернуть None, если чужой."""
    r = _norm(rel).replace(" ", "_")
    if r in RELATION_VOCAB:
        return r
    return _REL_SYNONYMS.get(_norm(rel))


def extract_graph(chunks, llm, max_chunks=12, query=None, log=lambda *a: None):
    """chunks → (facts, stats). Каждый факт заземлён цитатой в конкретном фрагменте.

    query (обычно KPI): лексический префильтр — извлекаем граф из фрагментов,
    релевантных цели, а не из самых длинных. Полностью автоматически, без LLM."""
    selected = _select(chunks, max_chunks, query)
    facts, stats = [], {"chunks": len(selected), "raw": 0, "kept": 0, "dropped": 0}
    for idx, ch in enumerate(selected, 1):
        text = ch["text"]
        if len(text) < 40:
            continue
        try:
            raw = llm.complete(SYSTEM, PROMPT.format(chunk=text[:3500], relations=RELATION_LIST))
            triplets = extract_json(raw) or []
        except Exception as e:  # noqa: BLE001
            log(f"  фрагмент {idx}: ошибка LLM ({e})")
            continue
        if not isinstance(triplets, list):
            continue
        norm_text = _norm(text)
        kept_here = 0
        for t in triplets:
            stats["raw"] += 1
            q = _norm(t.get("quote", ""))
            subj, obj = t.get("subject", ""), t.get("object", "")
            rel = _canon_relation(t.get("relation", ""))
            # гейт: (1) есть сущности, (2) тип связи из словаря, (3) дословная цитата
            if not (subj and obj) or rel is None or len(q) < 8 or q not in norm_text:
                stats["dropped"] += 1
                continue
            facts.append({
                "subject": subj.strip(), "relation": rel,
                "sign": RELATION_VOCAB[rel],  # знак ДЕТЕРМИНИРОВАН словарём, не от LLM
                "object": obj.strip(), "quote": t.get("quote", "").strip(),
                "source": ch["source"], "locator": ch["locator"],
            })
            kept_here += 1
        stats["kept"] += kept_here
        log(f"  фрагмент {idx}/{len(selected)} [{ch['locator']}]: "
            f"принято {kept_here} связей")
    return facts, stats


def _alpha_ratio(t):
    letters = sum(ch.isalpha() for ch in t)
    return letters / max(len(t), 1)


def _tokens(s):
    return set(re.findall(r"[а-яёa-z]{4,}", (s or "").lower()))


def _select(chunks, max_chunks, query=None):
    """Отобрать прозаические фрагменты, релевантные цели (лексически), не самые длинные.
    Для демо ограничиваем число вызовов LLM; в проде обрабатываются все."""
    prose = [c for c in chunks
             if c.get("kind", "prose") == "prose"
             and len(c.get("text", "")) >= 200
             and _alpha_ratio(c["text"]) >= 0.55]
    if query:
        qt = _tokens(query)
        def relevance(c):
            overlap = len(_tokens(c["text"]) & qt)
            return overlap + 0.001 * _alpha_ratio(c["text"])  # тай-брейк
        prose.sort(key=lambda c: -relevance(c))
    else:
        prose.sort(key=lambda c: -_alpha_ratio(c["text"]) * len(c["text"]) ** 0.5)
    return prose[:max_chunks]


DATA_SYSTEM = (
    "Ты — технолог обогащения. По таблице анализа хвостов определяешь, ГДЕ и СКОЛЬКО "
    "теряется ИЗВЛЕКАЕМОГО ценного металла. Ничего не выдумываешь — только из таблицы. "
    "Ответ — ТОЛЬКО JSON-массив."
)
DATA_PROMPT = """Ниже строки таблицы анализа хвостов обогащения (класс крупности,
доли, тонны по элементам, минеральные формы). Найди КЛЮЧЕВЫЕ потери ИЗВЛЕКАЕМОГО
металла: в каком классе крупности и в какой форме (раскрытый/закрытый минерал) сидит
потеря и сколько (тонн или %). До 6 фактов.
Каждый — объект строго с полями:
"finding" — краткий вывод (напр.: "в крупном классе +125 много закрытого пентландита"),
"size_class" — класс крупности, если есть (напр. "+125", "-10"),
"quote" — ДОСЛОВНАЯ строка из таблицы ниже (скопируй буквально).
Верни ТОЛЬКО JSON-массив.

ТАБЛИЦА:
\"\"\"
{table}
\"\"\""""


def extract_data_facts(table_chunks, llm, log=lambda *a: None):
    """Таблицы (Excel) → факты потерь, заземлённые цитатой строки. Автоматически,
    без ручной схемы: LLM читает строки, цитатный гейт проверяет дословность."""
    facts, stats = [], {"chunks": 0, "raw": 0, "kept": 0, "dropped": 0}
    for ch in table_chunks:
        text = ch.get("text", "")
        if len(text) < 40:
            continue
        stats["chunks"] += 1
        try:
            raw = llm.complete(DATA_SYSTEM, DATA_PROMPT.format(table=text[:6000]))
            items = extract_json(raw) or []
        except Exception as e:  # noqa: BLE001
            log(f"  таблица [{ch['locator']}]: ошибка LLM ({e})")
            continue
        if not isinstance(items, list):
            continue
        norm_text = _norm(text)
        kept_here = 0
        for it in items:
            stats["raw"] += 1
            q = _norm(it.get("quote", ""))
            finding = (it.get("finding") or "").strip()
            if not finding or len(q) < 6 or q not in norm_text:
                stats["dropped"] += 1
                continue
            sc = (it.get("size_class") or "").strip()
            facts.append({
                "subject": (f"потери извлекаемого металла в классе {sc}".strip()
                            if sc else "потери извлекаемого металла"),
                "relation": "связан", "sign": 0,
                "object": finding, "quote": it.get("quote", "").strip(),
                "source": ch["source"], "locator": ch["locator"], "kind": "data",
                "finding": finding, "size_class": sc,
            })
            kept_here += 1
        stats["kept"] += kept_here
        log(f"  таблица [{ch['locator']}]: принято {kept_here} фактов потерь")
    return facts, stats


def build_adjacency(facts):
    """Простой граф: subject → [(object, fact)]. Домен-независимо."""
    adj = {}
    for f in facts:
        adj.setdefault(f["subject"].lower(), []).append((f["object"].lower(), f))
    return adj
