#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ОСНОВНОЙ БЕЙЗЛАЙН · Автоматическая grounded-фабрика гипотез.

Человек делает ТОЛЬКО две вещи: кладёт материалы в папку и задаёт KPI.
Дальше всё автоматически — никаких конфигов и фактов руками:

  1. ПРИЁМ  — авто-парсинг всех файлов папки (PDF/XLSX/DOCX/TXT) с провенансом.
  2. ЗНАНИЕ — LLM извлекает граф причинно-следственных связей, ЦИТАТНЫЙ ГЕЙТ
             отсекает всё, что не подтверждено дословной цитатой из источника.
  3. НОВИЗНА — каждая связь векторизуется (эмбеддинги) → «карта известного».
  4. ГЕНЕРАЦИЯ — по KPI извлекаем релевантные связи и просим LLM собрать
             ПРОВЕРЯЕМЫЕ гипотезы СТРОГО из них (RAG, grounded).
  5. КРИТИК — гипотеза без ссылки на реальные извлечённые факты отбраковывается.
  6. ОЦЕНКА — измеримая новизна = расстояние гипотезы до ближайшего известного
             факта в корпусе (+ показываем сам ближайший факт), value/risk от LLM.
  7. РАНЖИРОВАНИЕ и карточки ЕСЛИ/ТО/ПОТОМУ ЧТО с цитатами до страницы/ячейки.

Кэш (--cache) хранит извлечённый граф и эмбеддинги, чтобы демо было мгновенным и
чтобы не звать LLM повторно.

Запуск:
    uv run python run.py --materials ../materials --kpi "снизить потери никеля с хвостами"
    uv run python run.py --materials <любая папка> --kpi "<любой KPI>"

Секреты — из baselines/.env. Библиотеки: pymupdf, openpyxl (через uv).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common import extract, ingest              # noqa: E402
from common.llm import Yandex, cosine, extract_json  # noqa: E402

_n = [0]
def step(msg):
    _n[0] += 1; print(f"\n[{_n[0]}] ── {msg}")
def sub(msg):
    print(f"       {msg}")

GEN_SYSTEM = (
    "Ты — инженер-технолог обогатительной фабрики. Предлагаешь ИНЖЕНЕРНЫЕ гипотезы "
    "СТРОГО из поданных фактов. Запрещено вводить факты вне списка. "
    "Ответ — ТОЛЬКО валидный JSON-массив."
)
GEN_PROMPT = """Цель (KPI): {kpi}

ФАКТЫ (используй только их, ссылайся по id):
{facts}

Предложи ОТ 6 ДО 12 ПРОВЕРЯЕМЫХ ИНЖЕНЕРНЫХ гипотез. Обязательно ПОКРОЙ РАЗНЫЕ
СЕМЕЙСТВА вмешательств и разные классы крупности из данных:
- измельчение/раскрытие (геометрия футеровки мельниц, доизмельчение, гранулометрия) —
  для закрытых сростков (закрытый Pnt/Cp) в крупных классах;
- классификация (гидроциклоны, песковые насадки, замена/донастройка классификаторов,
  контрольная классификация, возврат хвостов в голову) — для перераспределения
  целевого класса;
- грохочение целевого/тонкого класса (тонкое грохочение);
- схема флотации (время флотации, контактные чаны, перечистки, перераспределение фронта);
- реагентный режим.
Каждая гипотеза устраняет КОНКРЕТНУЮ потерю из фактов и указывает класс крупности
(напр.: закрытый минерал в крупном классе → доизмельчение/футеровка; раскрытый минерал
в тонком классе → тонкое грохочение/гидроциклоны/контрольная классификация).
Каждая — объект строго с полями:
"if"        — конкретное инженерное вмешательство,
"then"      — ожидаемый эффект на KPI,
"because"   — механизм (через какие факты),
"uses_facts"— массив id использованных фактов (["k1","k4"]),
"experiment"— краткий протокол проверки.
Оценки НЕ ставь — их считает система. Верни ТОЛЬКО JSON-массив."""


# ─────────────────────────────────────────────────────────────────────────────
def build_knowledge(materials, llm, max_chunks, cache_path, query=None):
    if cache_path and os.path.exists(cache_path):
        sub(f"кэш найден: {os.path.basename(cache_path)} — использую его")
        return json.load(open(cache_path, encoding="utf-8"))

    chunks = ingest.split_chunks(ingest.ingest_dir(materials))
    prose = [c for c in chunks if c.get("kind") == "prose"]
    tables = [c for c in chunks if c.get("kind") == "table"]
    sub(f"файлов→фрагментов: {len(chunks)} (проза {len(prose)}, таблицы {len(tables)})")

    facts, stats = extract.extract_graph(chunks, llm, max_chunks=max_chunks,
                                         query=query, log=sub)
    sub(f"извлечено связей из прозы: {stats['kept']} (сырых {stats['raw']}, "
        f"отброшено цитатным гейтом {stats['dropped']})")

    # ДАННЫЕ: авто-диагностика таблиц (где теряется извлекаемый металл) — основа
    # инженерных гипотез. Тоже с цитатным гейтом (дословная строка таблицы).
    data_facts, dstats = extract.extract_data_facts(tables, llm, log=sub)
    if data_facts:
        sub(f"извлечено фактов потерь из таблиц: {dstats['kept']} "
            f"(отброшено {dstats['dropped']})")
        facts = facts + data_facts
        stats["kept"] += dstats["kept"]
        stats["dropped"] += dstats["dropped"]
        stats["data_facts"] = dstats["kept"]

    # эмбеддинги фактов для карты новизны
    for i, f in enumerate(facts):
        f["id"] = f"k{i + 1}"
        if f.get("kind") == "data":       # факт-данные: чистый текст вывода
            sc = f.get("size_class", "")
            f["text"] = (f"класс {sc}: {f.get('finding','')}".strip(": ")
                         if sc else f.get("finding", ""))
        else:
            f["text"] = f"{f['subject']} {f['relation']} {f['object']}"
        f["emb"] = llm.embed(f["text"], kind="doc")
    kb = {"facts": facts, "stats": stats}
    if cache_path:
        json.dump(kb, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)
    return kb


def retrieve(kb, kpi, kpi_emb, k_data=10, k_prose=8):
    """Контекст генерации = ДАННЫЕ (где теряется металл — диагностический костяк,
    всегда присутствуют) + ПРОЗА (механизмы из литературы). Оба по релевантности к KPI.

    Если в KPI назван объект (напр. «ТОФ»), совпадающий с именем файла данных —
    берём факты потерь ТОЛЬКО этой фабрики (иначе мешаются данные всех фабрик)."""
    import re
    data = [f for f in kb["facts"] if f.get("kind") == "data"]
    prose = [f for f in kb["facts"] if f.get("kind") != "data"]
    tokens = set(re.findall(r"[A-ZА-ЯЁ]{2,}", kpi))  # ТОФ, КГМК, НОФ …
    focused = [f for f in data if any(t in f.get("source", "") for t in tokens)]
    if focused:
        data = focused
    data.sort(key=lambda f: -cosine(kpi_emb, f.get("emb", [])))
    prose.sort(key=lambda f: -cosine(kpi_emb, f.get("emb", [])))
    return data[:k_data] + prose[:k_prose]


def compute_metrics(h, valid, kb, kpi_emb, llm):
    """Все метрики считаются ДЕТЕРМИНИРОВАННО (не LLM). Возвращает раскладку.

    relevance  — средний косинус используемых фактов к KPI (насколько по теме);
    novelty    — 1 - близость гипотезы к ближайшему ДРУГОМУ известному факту;
    support    — число независимых источников (страниц/файлов) под гипотезой;
    sign_risk  — выше, если знак связи нейтральный/неоднозначный (0);
    support_risk — выше при единственном источнике;
    risk       — среднее компонентов риска;
    score      — relevance · (1 - risk) · (0.5 + 0.5 · novelty).
    """
    used = [valid[i] for i in h["_used"]]
    if not used:
        return {"relevance": 0.0, "novelty": 0.0, "support": 0, "signs": [],
                "sign_risk": 1.0, "support_risk": 1.0, "risk": 1.0, "score": 0.0,
                "nearest": None}
    relevance = round(sum(cosine(kpi_emb, f.get("emb", [])) for f in used) / len(used), 3)
    signs = [f.get("sign", 0) for f in used]
    support = len({f["locator"] for f in used})
    nov, nearest = novelty_of(f"{h.get('if','')} {h.get('then','')}", kb, llm,
                              exclude_ids=set(h["_used"]))
    # риск ниже, если есть направленный механизм (±1); наблюдения-данные (sign 0)
    # не штрафуем поштучно — важно лишь, подкреплена ли гипотеза механизмом.
    has_direction = any(s != 0 for s in signs)
    sign_risk = 0.2 if has_direction else 0.35
    support_risk = 0.5 if support < 2 else 0.25
    risk = round((sign_risk + support_risk) / 2, 3)
    score = round(max(relevance, 0.0) * (1 - risk) * (0.5 + 0.5 * nov), 3)
    return {"relevance": relevance, "novelty": nov, "support": support, "signs": signs,
            "sign_risk": sign_risk, "support_risk": support_risk, "risk": risk,
            "score": score, "nearest": nearest}


def novelty_of(text, kb, llm, exclude_ids=()):
    """Измеримая новизна = 1 - близость к ближайшему ДРУГОМУ известному решению.

    Факты, из которых собрана гипотеза (exclude_ids), исключаются — иначе ближайшим
    оказывается сам факт-источник и новизна получается искусственно заниженной.
    Возвращаем и сам ближайший аналог (для «рядом показать ближайшую работу»)."""
    e = llm.embed(text, kind="query")
    best, bestf = -1.0, None
    for f in kb["facts"]:
        if f.get("id") in exclude_ids:
            continue
        c = cosine(e, f.get("emb", []))
        if c > best:
            best, bestf = c, f
    return round(1 - best, 3), bestf


# ─────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--materials", default=os.path.join(os.path.dirname(__file__), "..", "materials"))
    ap.add_argument("--kpi", default="снизить потери никеля (Ni) с отвальными хвостами флотации")
    ap.add_argument("--max-chunks", type=int, default=10)
    ap.add_argument("--cache", default=os.path.join(os.path.dirname(__file__), "kb_cache.json"))
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    print("=" * 78)
    print("АВТОМАТИЧЕСКАЯ GROUNDED-ФАБРИКА ГИПОТЕЗ")
    print(f"материалы: {args.materials}\nKPI: {args.kpi}")
    print("=" * 78)

    # temperature=0 → воспроизводимость: тот же корпус+KPI → тот же граф и гипотезы.
    # Плюс граф кэшируется. temp — знобка (выше = разнообразнее, ниже = стабильнее).
    # max_tokens повыше — чтобы 6-12 гипотез в ответе не обрезались.
    llm = Yandex(model="yandexgpt/latest", temperature=0.0, max_tokens=4000)
    if not llm.ready:
        print("Нет ключа Yandex в .env — пайплайн требует LLM. Останов."); return

    t_start = time.perf_counter()
    phases = {}

    step("ПРИЁМ + ЗНАНИЕ: авто-парсинг материалов и извлечение графа связей")
    _t = time.perf_counter()
    kb = build_knowledge(args.materials, llm,
                         max_chunks=args.max_chunks,
                         cache_path=None if args.no_cache else args.cache,
                         query=args.kpi)
    phases["знание (ingest+extract)"] = time.perf_counter() - _t
    if not kb["facts"]:
        print("Из материалов не извлечено ни одной подтверждённой связи."); return
    sub("примеры извлечённых связей (с источником):")
    for f in kb["facts"][:5]:
        sub(f"  ({f['subject']}) →{f['sign']}→ ({f['object']})  [{f['locator']}]")

    step(f"НОВИЗНА: карта известного построена ({len(kb['facts'])} связей векторизованы)")

    step("ГЕНЕРАЦИЯ: извлекаю релевантные KPI связи и прошу LLM собрать гипотезы")
    _t = time.perf_counter()
    kpi_emb = llm.embed(args.kpi, kind="query")
    top = retrieve(kb, args.kpi, kpi_emb, k_data=10, k_prose=8)
    n_data = sum(1 for f in top if f.get("kind") == "data")
    srcs = sorted({f["source"] for f in top if f.get("kind") == "data"})
    sub(f"контекст: {n_data} фактов-данных (потери) + {len(top)-n_data} прозы (механизмы)")
    sub(f"данные из: {', '.join(srcs) or '—'}")
    facts_txt = "\n".join(f'- [{f["id"]}] {f["text"]} (источник: {f["locator"]})' for f in top)
    raw = llm.complete(GEN_SYSTEM, GEN_PROMPT.format(kpi=args.kpi, facts=facts_txt))
    hyps = extract_json(raw)
    if not isinstance(hyps, list):
        print("LLM не вернул валидный список гипотез."); print(raw[:500]); return
    sub(f"сгенерировано кандидатов: {len(hyps)}")

    step("КРИТИК (grounding-гейт): проверяю ссылки на реальные факты")
    valid = {f["id"]: f for f in top}
    for h in hyps:
        used = [i for i in h.get("uses_facts", []) if i in valid]
        h["_used"] = used
        h["_grounded"] = bool(used)
    ok = sum(h["_grounded"] for h in hyps)
    sub(f"заземлено {ok}/{len(hyps)}")

    step("ОЦЕНКА (все метрики считаются детерминированно, НЕ LLM) и ранжирование")
    for h in hyps:
        h["_metrics"] = compute_metrics(h, valid, kb, kpi_emb, llm)
    hyps.sort(key=lambda h: (-int(h["_grounded"]), -h["_metrics"]["score"]))
    sub("формула: score = relevance · (1 − risk) · (0.5 + 0.5·novelty)")
    phases["генерация+оценка"] = time.perf_counter() - _t

    step("РАНЖИРОВАННЫЕ ГИПОТЕЗЫ (ЕСЛИ / ТО / ПОТОМУ ЧТО) + полная раскладка метрик:")
    for i, h in enumerate(hyps, 1):
        m = h["_metrics"]
        flag = "" if h["_grounded"] else "  ⚠ НЕ ЗАЗЕМЛЕНА"
        print(f"\n   #{i}  SCORE={m['score']}{flag}")
        print(f"       ЕСЛИ:  {h.get('if')}")
        print(f"       ТО:    {h.get('then')}")
        print(f"       П.Ч.:  {h.get('because')}")
        print(f"       эксперимент: {h.get('experiment')}")
        print(f"       метрики: relevance={m['relevance']} (близость к KPI) · "
              f"novelty={m['novelty']} · support={m['support']} источн. · "
              f"risk={m['risk']} (знак={m['sign_risk']}, опора={m['support_risk']})")
        print(f"       знаки связей: {m['signs']}")
        for fid in h["_used"]:
            f = valid[fid]
            print(f"       ↳ факт [{f['locator']}] ({f['relation']},{f['sign']:+d}): "
                  f"«{f['quote'][:90]}»")
        if m.get("nearest"):
            print(f"       ближайшее ДРУГОЕ известное: «{m['nearest']['text']}» "
                  f"[{m['nearest']['locator']}]")

    # ── ТЕХНИЧЕСКИЕ МЕТРИКИ (токены, вызовы, время) ──
    total_s = time.perf_counter() - t_start
    s = llm.stats
    tech = {
        "total_seconds": round(total_s, 1),
        "api_seconds": round(s["api_seconds"], 1),
        "phases": {k: round(v, 1) for k, v in phases.items()},
        "llm_calls": s["completion_calls"],
        "embed_calls": s["embed_calls"],
        "input_tokens": s["input_tokens"],
        "completion_tokens": s["completion_tokens"],
        "total_tokens": s["total_tokens"],
        "embed_tokens": s["embed_tokens"],
        "model": llm.model,
    }
    step("ТЕХНИЧЕСКИЕ МЕТРИКИ")
    sub(f"время всего: {tech['total_seconds']} c (из них API: {tech['api_seconds']} c)")
    for k, v in tech["phases"].items():
        sub(f"  · {k}: {v} c")
    sub(f"вызовов LLM: {tech['llm_calls']} | эмбеддингов: {tech['embed_calls']}")
    sub(f"токены LLM: вход {tech['input_tokens']} + выход {tech['completion_tokens']} "
        f"= {tech['total_tokens']} | токены эмбеддингов: {tech['embed_tokens']}")

    # чистый вывод без эмбеддингов (иначе JSON раздувается векторами)
    def clean_fact(f):
        return {k: v for k, v in f.items() if k != "emb"}
    export = []
    for h in hyps:
        m = dict(h["_metrics"])
        m["nearest"] = clean_fact(m["nearest"]) if m.get("nearest") else None
        export.append({
            "if": h.get("if"), "then": h.get("then"), "because": h.get("because"),
            "experiment": h.get("experiment"), "grounded": h["_grounded"],
            "facts": [clean_fact(valid[i]) for i in h["_used"]],
            "metrics": m,
        })
    out = os.path.join(os.path.dirname(__file__), "hypotheses.json")
    json.dump(export, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nСохранено: {os.path.basename(out)} (без эмбеддингов)")

    # HTML-отчёт (минималистичный, самодостаточный — открывается двойным кликом)
    from common.report import render
    html_path = os.path.join(os.path.dirname(__file__), "report.html")
    open(html_path, "w", encoding="utf-8").write(
        render(export, args.kpi, materials=args.materials,
               stats=kb.get("stats"), tech=tech))
    print(f"HTML-отчёт: {os.path.basename(html_path)} (открой в браузере)")
    print("\n" + "=" * 78)
    print("Всё авто: человек дал папку + KPI. Конфиги/факты руками не писались.")
    print("=" * 78)


if __name__ == "__main__":
    main()
