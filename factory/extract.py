# -*- coding: utf-8 -*-
"""Извлечение сущностей и связей из ТЕКСТА через LLM + ЦИТАТНЫЙ ГЕЙТ + кэш.

Это слой понимания неструктурированных данных (статьи/патенты/отчёты). LLM читает
фрагмент и возвращает связи (subject —тип→ object) с дословной цитатой. Связь
принимается ТОЛЬКО если цитата реально есть во фрагменте → выдумки отсекаются.
После кэширования весь downstream детерминирован (тот же кэш → тот же граф).

Кэш несёт отпечаток (KPI + выбранные фрагменты): смена запроса или корпуса
автоматически инвалидирует его. LLM-вызовы идут параллельно (LLM_WORKERS),
результат собирается в порядке фрагментов → вывод детерминирован.

Структура НЕ хардкодится: работает на любом тексте; тип связи выбирается из закрытого
словаря, поэтому знак влияния детерминирован (критик знаков не нужен).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

from factory.config import LLM_WORKERS, MAX_CHUNK_CHARS, MIN_PROSE_CHARS
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


def _quote_ok(q, nt, fuzzy):
    """Цитата в тексте? Для OCR-чанков — мягко (≥80% слов), т.к. распознавание шумит."""
    if q in nt:
        return True
    if not fuzzy:
        return False
    toks = re.findall(r"[а-яёa-z0-9]{3,}", q)
    if len(toks) < 3:
        return False
    return sum(1 for w in toks if w in nt) / len(toks) >= 0.8


def _select(chunks, max_chunks, query):
    prose = [c for c in chunks if c.kind == "prose" and len(c.text) >= MIN_PROSE_CHARS
             and sum(ch.isalpha() for ch in c.text) / max(len(c.text), 1) >= 0.55]
    if query:
        qt = _tokens(query)
        prose.sort(key=lambda c: -len(_tokens(c.text) & qt))
    else:
        prose.sort(key=lambda c: -len(c.text))
    return prose[:max_chunks]


def _fingerprint(selected, query):
    """Отпечаток входа: KPI + выбранные фрагменты. Меняется вход → кэш недействителен."""
    h = hashlib.sha256((query or "").encode("utf-8"))
    for c in selected:
        h.update(c.text[:MAX_CHUNK_CHARS].encode("utf-8"))
    return h.hexdigest()[:16]


def _load_cache(cache_path, fp, log):
    if not (cache_path and os.path.exists(cache_path)):
        return None
    cached = json.load(open(cache_path, encoding="utf-8"))
    if isinstance(cached, list):                 # старый формат — без отпечатка
        if cached:
            log(f"кэш графа (legacy): {os.path.basename(cache_path)} ({len(cached)} связей)")
            return cached
        return None
    rels = cached.get("relations") or []
    if cached.get("fingerprint") != fp:
        log("кэш от другого входа (KPI/корпус изменились) — переизвлекаю")
        return None
    if rels:
        log(f"кэш графа: {os.path.basename(cache_path)} ({len(rels)} связей)")
        return rels
    return None


def _ask(llm, chunk):
    """Один LLM-вызов; исключение возвращаем значением (для параллельного map)."""
    try:
        raw = llm.complete(SYSTEM, PROMPT.format(chunk=chunk.text[:MAX_CHUNK_CHARS],
                                                 rel=", ".join(RELATION_VOCAB)))
        return extract_json(raw) or []
    except Exception as e:  # noqa: BLE001
        return e


def extract_relations(chunks, llm=None, max_chunks=12, query=None,
                      cache_path=None, log=lambda *a: None):
    """chunks → список связей с провенансом. Кэш делает downstream детерминированным."""
    selected = _select(chunks, max_chunks, query)
    fp = _fingerprint(selected, query)
    cached = _load_cache(cache_path, fp, log)
    if cached is not None:
        return cached

    llm = llm or Yandex(temperature=0.0)
    if not llm.ready:
        raise RuntimeError("нет ключа Yandex (.env) — извлечение из текста требует LLM")

    # параллельные вызовы; map отдаёт результаты в порядке фрагментов → детерминизм
    workers = max(1, min(LLM_WORKERS, len(selected)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        answers = list(ex.map(lambda c: _ask(llm, c), selected))

    rels, stats = [], {"raw": 0, "kept": 0, "dropped": 0}
    for i, (c, triples) in enumerate(zip(selected, answers), 1):
        if isinstance(triples, Exception):
            log(f"  фрагмент {i}: ошибка LLM ({triples})"); continue
        if not isinstance(triples, list):
            continue
        nt = _norm(c.text); kept = 0
        ocr = bool((c.meta or {}).get("ocr"))       # OCR-чанк → мягкий цитатный гейт
        for t in triples:
            stats["raw"] += 1
            q = _norm(t.get("quote", "")); rel = _canon_rel(t.get("relation", ""))
            subj, obj = t.get("subject", ""), t.get("object", "")
            if not (subj and obj) or rel is None or len(q) < 8 or not _quote_ok(q, nt, ocr):
                stats["dropped"] += 1; continue
            rels.append({"subject": subj.strip(), "relation": rel,
                         "sign": RELATION_VOCAB[rel], "object": obj.strip(),
                         "quote": t.get("quote", "").strip(),
                         "source": c.source, "locator": c.locator, "meta": c.meta})
            kept += 1
        stats["kept"] += kept
        log(f"  {i}/{len(selected)} [{c.locator}]: +{kept} связей")
    log(f"извлечено {stats['kept']} связей (сырых {stats['raw']}, "
        f"отброшено гейтом {stats['dropped']})")
    if cache_path and rels:              # пустой результат не кэшируем
        json.dump({"fingerprint": fp, "relations": rels},
                  open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rels
