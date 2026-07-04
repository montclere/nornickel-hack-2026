# -*- coding: utf-8 -*-
"""Гибкий приём: загрузи ЧТО УГОДНО (папка/файлы) → система разбирается сама.

Диспетчер по типу данных:
  • отчёт по хвостам (xlsx со структурой) → ДЕТЕРМИНИРОВАННАЯ диагностика (factory core);
  • прочий текст (PDF/DOCX/TXT/патенты/статьи) → LLM-извлечение связей (цитатный гейт,
    кэш) → канонический граф → разрывы Свонсона (детерминированно поверх кэша).

Так закрывается требование ТЗ «гибкость входных данных»: детерминизм — в рассуждении,
LLM — только в понимании неструктурированного текста, с заземлением до цитаты/страницы.

Единственная команда, которая СОХРАНЯЕТ конфиг запуска (см. runconfig.py) — так
benchmark.py/judge.py могут переиспользовать этот же KPI без copy-paste, если явно не
передан свой. Единственная команда, которая реально зовёт LLM на извлечение (остальные
только читают кэш).

Если в этом же прогоне нашлась ветка А (хвосты) — запрос к литературе ОБОГАЩАЕТСЯ
терминами уже посчитанного диагноза (семейство вмешательства + минеральная форма),
чтобы искать решения именно под то, что реально нашли в данных, а не по общим словам
KPI. Если ветки А нет (только разрозненная литература/схемы без структурных данных) —
ветка Б работает САМОСТОЯТЕЛЬНО на голом KPI, как раньше — это не регрессия, а честный
fallback.

Запуск:
    uv run python -m factory.flex materials --kpi "снизить потери никеля с хвостами"
    uv run python -m factory.flex materials/knowledge/books --kpi "повысить извлечение Ni"
"""
from __future__ import annotations

import argparse
import os
import time

from factory.config import DEFAULT_CACHE, MIN_PROSE_CHARS, OUTPUTS_DIR, RUN_CONFIG_PATH
from factory.ingest import ingest, split
from factory.runconfig import RunConfig, save_run_config


def _is_tailings(path):
    """Отчёт по хвостам? Пробуем специализированный ридер — есть ли классы крупности."""
    if not path.lower().endswith(".xlsx"):
        return False
    try:
        from factory.reader import TailingsReader
        return len(TailingsReader(path).read().classes) >= 3
    except Exception:  # noqa: BLE001
        return False


def _diagnosis_query_terms(all_hyps, limit=4):
    """Термины уже посчитанного диагноза ветки А — обогатить запрос к литературе.
    Пусто, если гипотез нет (вызывающий код тогда просто не трогает исходный KPI)."""
    if not all_hyps:
        return ""
    fams = sorted({h.family for h in all_hyps})[:limit]
    forms = sorted({h.dominant_form for h in all_hyps if h.dominant_form})[:limit]
    return " ".join(fams + forms)


def main():
    ap = argparse.ArgumentParser(description="Гибкая фабрика гипотез (загрузи что угодно)")
    ap.add_argument("paths", nargs="+", help="файлы или папки с материалами")
    ap.add_argument("--kpi", required=True, help="обязателен: без цели неясно, что "
                    "оптимизировать и как ранжировать гипотезы")
    ap.add_argument("--max-chunks", type=int, default=14)
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--web", action="store_true",
                    help="искать в интернете мировые практики (заполняет world_practice "
                    "гипотез внешней цитатой + URL; кэшируется, требует ключа Yandex)")
    ap.add_argument("--run-config", default=RUN_CONFIG_PATH,
                    help="куда сохранить конфиг этого запуска (KPI+параметры) — его "
                    "подхватят benchmark/judge, если им не передать свой --kpi")
    args = ap.parse_args()

    save_run_config(RunConfig(kpi=args.kpi, materials_paths=args.paths,
                              cache_path=args.cache, max_chunks=args.max_chunks,
                              timestamp=time.strftime("%Y-%m-%d %H:%M:%S")),
                    args.run_config)

    # разбираем KPI сразу — чтобы честно предупредить, если целевой элемент не распознан
    # или его нет в схеме отчёта (иначе ветка А молча выдаст никель под видом ответа)
    from factory.intent import parse_intent, warn_intent
    intent = parse_intent(args.kpi)
    skip_branch_a = warn_intent(intent, args.kpi, emit=lambda m: print("\n" + m))

    print("=" * 74)
    print("ГИБКИЙ ПРИЁМ МАТЕРИАЛОВ")
    print(f"KPI: {args.kpi}  (целевой элемент: {intent.target_element}"
          f"{'' if intent.element_in_schema else ' — ВНЕ схемы хвостов'})")
    print(f"конфиг запуска сохранён: {args.run_config} "
          f"(его переиспользуют benchmark/judge без --kpi)")
    print("=" * 74)

    # --- собрать все файлы, отделить отчёты по хвостам от прочего текста ---
    all_files = []
    for p in args.paths:
        if not os.path.exists(p):
            print(f"\n⚠ путь не существует: {p} — пропущен.")
            continue
        if os.path.isdir(p):
            for root, _, fs in os.walk(p):
                all_files += [os.path.join(root, f) for f in fs]
        else:
            all_files.append(p)
    tailings = [f for f in sorted(set(all_files)) if _is_tailings(f)]
    # эталонные «Гипотезы*.docx» — это ОТВЕТЫ, не знание: не кормим их в извлечение
    others = [f for f in sorted(set(all_files))
              if f not in tailings and os.path.isfile(f)
              and "гипотез" not in os.path.basename(f).lower()]

    if not tailings and not others:
        print("\n⚠ МАТЕРИАЛОВ НЕ НАЙДЕНО по указанным путям — анализировать нечего.")
        print("  Проверьте пути и положите файлы (Хвосты*.xlsx и/или литературу) туда,")
        print("  на что указывают переданные аргументы.")
        return

    print(f"\nотчётов по хвостам (ветка А, состояние конкретных фабрик): {len(tailings)}")
    print(f"прочих материалов (ветка Б, знание): {len(others)}")

    # --- необязательный веб-поиск мировых практик (заполняет world_practice) ---
    web = None
    if args.web:
        from factory.websearch import WebPractices
        web = WebPractices(log=lambda m: print("  " + m))
        if not web.ready:
            print("\n⚠ --web запрошен, но веб-поиск недоступен (нет ключа Yandex или "
                  "FACTORY_WEB=0) — world_practice останется пустым.")
            web = None

    # --- ветка 1: детерминированная диагностика хвостов ---
    all_hyps = []
    if tailings and skip_branch_a:
        print("\n" + "─" * 74)
        print(f"ДИАГНОСТИКА ХВОСТОВ ПРОПУЩЕНА: целевого элемента "
              f"«{intent.requested_element}» нет в отчётах (см. предупреждение выше). "
              f"Работает только ветка Б (литература).")
        print("─" * 74)
    if tailings and not skip_branch_a:
        from factory.pipeline import HypothesisFactory
        print("\n" + "─" * 74)
        print("ДЕТЕРМИНИРОВАННАЯ ДИАГНОСТИКА ХВОСТОВ (без LLM)")
        print("─" * 74)
        for t in tailings:
            res = HypothesisFactory(t, kpi=args.kpi).run()
            p, hyps = res["profile"], res["hypotheses"]
            all_hyps.extend(hyps)
            # обогащаем мировыми практиками ДО отрисовки HTML — иначе в отчёт попадёт
            # пустой плейсхолдер; заодно html пересобираем уже с найденными цитатами
            if web:
                print(f"  · веб-поиск мировых практик для «{p.fabric}»…")
                web.enrich(hyps, extra=_diagnosis_query_terms(hyps))
                from factory.report import render
                res["html"] = render(p, res["graph"].to_layered(), hyps,
                                     kpi=args.kpi, tech=res.get("tech"),
                                     analysis=res.get("analysis"))
            os.makedirs(OUTPUTS_DIR, exist_ok=True)
            out = os.path.join(OUTPUTS_DIR, f"{p.fabric}_гипотезы.html")
            open(out, "w", encoding="utf-8").write(res["html"])
            top = hyps[0] if hyps else None
            print(f"  ■ {p.fabric}: {len(hyps)} гипотез; топ — {top.statement_if if top else '—'}")
            print(f"    → {out}")

    # --- ветка 2: извлечение из текста → граф → открытие ---
    if others:
        from factory.discover import discover
        from factory.extract import extract_relations
        from factory.kgraph import RelationGraph
        from factory.llm import Yandex
        print("\n" + "─" * 74)
        print("ИЗВЛЕЧЕНИЕ ИЗ ТЕКСТА → ГРАФ → РАЗРЫВЫ СВОНСОНА")
        print("─" * 74)
        chunks = split(ingest(others))
        prose = [c for c in chunks if c.kind == "prose" and len(c.text) >= MIN_PROSE_CHARS]
        n_state = sum(1 for c in prose if c.role == "state")
        print(f"текстовых фрагментов: {len(prose)} "
              f"(состояние фабрики: {n_state}, справочное: {len(prose) - n_state})")
        if n_state == 0:
            print("  · «состояние» здесь 0 — конвенция папок (state/fabrics/справочники/"
                  "reference) сейчас не задействована в этих путях, всё считается "
                  "справочным. Это НЕ ошибка, просто нечего было пометить как факт "
                  "про конкретную фабрику.")

        # если ветка А дала диагноз — ищем в литературе именно под НЕГО, а не по
        # общим словам KPI; если ветки А не было (нет структурных данных) — ветка Б
        # работает самостоятельно на голом KPI, без изменений
        extra = _diagnosis_query_terms(all_hyps)
        query = f"{args.kpi} {extra}".strip() if extra else args.kpi
        if extra:
            print(f"  запрос к литературе обогащён диагнозом ветки А: «{extra}»")
        else:
            print("  диагноза ветки А нет (нет структурных данных этой фабрики) — "
                  "ветка Б ищет самостоятельно по KPI")

        llm = Yandex(temperature=0.0)
        if not llm.ready:
            print("⚠ нет ключа Yandex (.env) — извлечение из текста недоступно. "
                  "Отчёты по хвостам работают без ключа.")
            return
        cache = None if args.no_cache else args.cache
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        rels = extract_relations(chunks, llm=llm, max_chunks=args.max_chunks,
                                 query=query, cache_path=cache, log=lambda m: print("  " + m))
        kg = RelationGraph(rels)
        print(f"канонический граф: {kg.stats()}")
        found = discover(kg, kpi=query, limit=8)
        print(f"\nнайдено гипотез-разрывов: {len(found)}")
        for i, d in enumerate(found, 1):
            tag = "состояние фабрики" if d.role == "state" else "справочное"
            print(f"\n  #{i} score={d.score} novelty={d.novelty} [{tag}]")
            print(f"     ЕСЛИ: {d.statement_if}")
            print(f"     ПЧ:   {d.statement_because}")
            print(f"     источники: {', '.join(s for s in d.sources if s)}")

    print("\n" + "=" * 74)
    print("Детерминизм — в рассуждении; LLM — только в понимании текста (с цитатным гейтом).")
    print("=" * 74)


if __name__ == "__main__":
    main()
