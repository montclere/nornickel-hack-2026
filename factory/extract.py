# -*- coding: utf-8 -*-
"""Извлечение сущностей и связей из ТЕКСТА через LLM + ЦИТАТНЫЙ ГЕЙТ + кэш.

Это слой понимания неструктурированных данных (статьи/патенты/отчёты). LLM читает
фрагмент и возвращает связи (subject —тип→ object) с дословной цитатой. Связь
принимается ТОЛЬКО если цитата реально есть во фрагменте → выдумки отсекаются.
После кэширования весь downstream детерминирован (тот же кэш → тот же граф).

Кэш несёт отпечаток (KPI + выбранные фрагменты): смена запроса или корпуса
автоматически инвалидирует его. LLM-вызовы идут параллельно (LLM_WORKERS), прогресс
логируется ПО МЕРЕ ЗАВЕРШЕНИЯ (as_completed), а не пачкой в конце; финальный список
связей всегда собирается в детерминированном порядке фрагментов, независимо от
порядка завершения запросов. Фрагменты, упавшие даже после backoff внутри одного
запроса, добираются ещё раз ПОСЛЕДОВАТЕЛЬНО (не толпой — см. FRAGMENT_RETRY_ATTEMPTS).

Единственное место в системе, которое реально зовёт LLM на извлечение — это
`extract_relations`, вызываемая из `flex.py`. judge.py/benchmark.py — только читают
уже готовый кэш через `load_cached_relations`, сами LLM не дёргают.

Структура НЕ хардкодится: работает на любом тексте; тип связи выбирается из закрытого
словаря, поэтому знак влияния детерминирован (критик знаков не нужен).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from factory.config import (FRAGMENT_RETRY_ATTEMPTS, LLM_WORKERS, MAX_CHUNK_CHARS,
                            MIN_PROSE_CHARS)
from factory.llm import Yandex, extract_json

# закрытый словарь типов связи → знак (LLM только ВЫБИРАЕТ тип, знак ставим мы)
RELATION_VOCAB = {"повышает": +1, "снижает": -1, "не_влияет": 0, "связан": 0}
_SYN = {"увеличивает": "повышает", "усиливает": "повышает", "улучшает": "повышает",
        "уменьшает": "снижает", "ослабляет": "снижает", "ухудшает": "снижает",
        "подавляет": "снижает", "не влияет": "не_влияет", "связано": "связан",
        "характеризует": "связан"}

SYSTEM = ("Ты — инженер-технолог обогатительной фабрики. Извлекаешь из текста "
          "проверяемые связи между сущностями (материалы, параметры, свойства, процессы), "
          "КЛАССИФИЦИРУЯ тип. ОСОБОЕ ВНИМАНИЕ к связям, где причина — это ДЕЙСТВИЕ, "
          "которое можно выполнить на промышленной фабрике (изменить оборудование, режим, "
          "дозировку реагента, параметр процесса), а не абстрактное научное свойство. "
          "Ничего не выдумываешь. Ответ — ТОЛЬКО JSON-массив.")
PROMPT = """Из фрагмента извлеки связи (до 5). Каждая — объект строго с полями:
"subject" — сущность-причина, "relation" — РОВНО ОДИН тип из [{rel}],
"object" — сущность-следствие, "quote" — ДОСЛОВНАЯ подстрока из фрагмента,
"is_action" — true, если subject описывает КОНКРЕТНОЕ ПРОМЫШЛЕННОЕ ДЕЙСТВИЕ/параметр,
которым управляет технолог (оборудование, реагент, режим, дозировка, крупность помола
и т.п.), false — если subject это абстрактное свойство/явление, которым нельзя
напрямую управлять (например «критическое значение pH» — false, но «изменение pH
добавлением извести» — true).
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
    """Строгое чтение для flex: отпечаток обязан совпасть, иначе кэш недействителен
    (мы всё равно можем переизвлечь — это единственное место, которое зовёт LLM)."""
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


def load_cached_relations(cache_path, log=lambda *a: None):
    """Read-only чтение кэша БЕЗ отпечатка и БЕЗ права на LLM-фоллбэк — для judge.py/
    benchmark.py: они только оценивают то, что уже наизвлекал flex. Несовпадение
    отпечатка здесь не блокирует — блокировать нечем, извлекать самим нельзя."""
    if not (cache_path and os.path.exists(cache_path)):
        log(f"нет кэша графа: {cache_path}")
        return None
    cached = json.load(open(cache_path, encoding="utf-8"))
    rels = cached if isinstance(cached, list) else (cached.get("relations") or [])
    if not rels:
        log(f"кэш графа пуст: {cache_path}")
        return None
    log(f"кэш графа: {os.path.basename(cache_path)} ({len(rels)} связей)")
    return rels


def _ask(llm, chunk):
    """Один LLM-вызов; исключение возвращаем значением (для параллельного пула)."""
    try:
        raw = llm.complete(SYSTEM, PROMPT.format(chunk=chunk.text[:MAX_CHUNK_CHARS],
                                                 rel=", ".join(RELATION_VOCAB)))
        return extract_json(raw) or []
    except Exception as e:  # noqa: BLE001
        return e


def _process_triples(c, triples):
    """Цитатный гейт: сырые триплеты фрагмента → (принятые связи, сырых, принято)."""
    if not isinstance(triples, list):
        return [], 0, 0
    nt = _norm(c.text)
    ocr = bool((c.meta or {}).get("ocr"))       # OCR-чанк → мягкий цитатный гейт (шум распознавания)
    out = []
    for t in triples:
        q = _norm(t.get("quote", "")); rel = _canon_rel(t.get("relation", ""))
        subj, obj = t.get("subject", ""), t.get("object", "")
        if not (subj and obj) or rel is None or len(q) < 8 or not _quote_ok(q, nt, ocr):
            continue
        out.append({"subject": subj.strip(), "relation": rel, "sign": RELATION_VOCAB[rel],
                    "object": obj.strip(), "quote": t.get("quote", "").strip(),
                    "is_action": bool(t.get("is_action", False)),  # промышленное действие?
                    "role": c.role,  # "state" (эта фабрика) vs "reference" (справочное)
                    "source": c.source, "locator": c.locator, "meta": c.meta})
    return out, len(triples), len(out)


def _fetch_all(llm, selected, log):
    """Параллельный запрос по всем фрагментам с потоковым логом (as_completed —
    печатаем СРАЗУ по готовности, а не после того, как отработает вся пачка).
    Возвращает список результатов в ИСХОДНОМ порядке фрагментов (детерминизм)."""
    n = len(selected)
    results = [None] * n
    workers = max(1, min(LLM_WORKERS, n))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_ask, llm, c): i for i, c in enumerate(selected)}
        for fut in as_completed(futures):
            i = futures[fut]
            results[i] = fut.result()
            c = selected[i]
            if isinstance(results[i], Exception):
                log(f"  {i+1}/{n} [{c.locator}]: ошибка ({results[i]})")
            else:
                _, raw, kept = _process_triples(c, results[i])
                log(f"  {i+1}/{n} [{c.locator}]: +{kept} связей")

    # добор упавших: ПОСЛЕДОВАТЕЛЬНО (не толпой) — параллельный повтор тем же расписанием
    # снова столкнёт все воркеры с лимитом в один момент
    failed = [i for i, r in enumerate(results) if isinstance(r, Exception)]
    for attempt in range(1, FRAGMENT_RETRY_ATTEMPTS + 1):
        failed = [i for i in failed if isinstance(results[i], Exception)]
        if not failed:
            break
        log(f"  повтор {attempt}/{FRAGMENT_RETRY_ATTEMPTS} для {len(failed)} "
            f"упавших фрагментов...")
        for i in failed:
            time.sleep(1.0 + random.uniform(0, 1.5))
            results[i] = _ask(llm, selected[i])
            c = selected[i]
            if isinstance(results[i], Exception):
                log(f"  {i+1}/{n} [{c.locator}]: снова ошибка ({results[i]})")
            else:
                _, raw, kept = _process_triples(c, results[i])
                log(f"  {i+1}/{n} [{c.locator}]: +{kept} связей (после повтора)")
    return results


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

    answers = _fetch_all(llm, selected, log)

    rels, stats = [], {"raw": 0, "kept": 0, "dropped": 0, "failed": 0}
    for c, triples in zip(selected, answers):
        if isinstance(triples, Exception):
            stats["failed"] += 1
            continue
        chunk_rels, raw, kept = _process_triples(c, triples)
        rels.extend(chunk_rels)
        stats["raw"] += raw; stats["kept"] += kept; stats["dropped"] += raw - kept
    log(f"извлечено {stats['kept']} связей (сырых {stats['raw']}, "
        f"отброшено гейтом {stats['dropped']}, не удалось получить "
        f"{stats['failed']}/{len(selected)})")
    if cache_path and rels:              # пустой результат не кэшируем
        json.dump({"fingerprint": fp, "relations": rels},
                  open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rels
