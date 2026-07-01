"""Извлечение триплетов из корпуса (BuildKnowledgeBase) → data/triplets.jsonl.

Прогоняет экстрактор по реальным статьям и синтетическим отчётам, применяет
цитатный гейт и пишет отчёт (извлечено / отброшено / по исходам).

Запуск (из корня; для real-извлечения нужен GROQ_API_KEY в окружении/.env):

    python scripts/extract_facts.py                 # 12 статей + отчёты, режим real
    python scripts/extract_facts.py --articles 5    # меньше статей (экономия квоты)
    PHOENIX_EXTRACT=fake python scripts/extract_facts.py   # оффлайн на фикстурах
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config import DATA_DIR
from app.container import build
from app.service.entities import Document, Triplet


def _load(path: Path) -> list[Document]:
    if not path.exists():
        sys.exit(f"Нет {path}. Сначала соберите корпус: python scripts/build_corpus.py")
    return [Document(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Извлечение триплетов из корпуса")
    parser.add_argument("--articles", type=int, default=12, help="сколько статей OpenAlex обработать")
    parser.add_argument("--no-reports", action="store_true", help="не обрабатывать синтетические отчёты")
    parser.add_argument("--mode", default="real", help="режим контейнера (real|fake|mix)")
    args = parser.parse_args()

    corpus = _load(DATA_DIR / "corpus.jsonl")
    reports = _load(DATA_DIR / "reports.jsonl")

    # берём документы с текстом (сканы без OCR пропускаем — это задача OCR-адаптера)
    articles = [d for d in corpus if d.text][: args.articles]
    report_docs = [] if args.no_reports else [d for d in reports if d.text]
    docs = articles + report_docs

    container = build(args.mode)
    bkb = container.build_knowledge_base
    print(f"Экстрактор: {container.adapter_modes.get('extractor')}")
    print(f"Документов к обработке: {len(docs)} ({len(articles)} статей + {len(report_docs)} отчётов)\n")

    triplets: list[Triplet] = []
    for i, doc in enumerate(docs, 1):
        triplets.extend(bkb.execute([doc]))
        print(f"  [{i}/{len(docs)}] {doc.id}: всего триплетов {len(triplets)}", end="\r")
    print()

    out = DATA_DIR / "triplets.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for t in triplets:
            f.write(t.model_dump_json() + "\n")

    _report(container, docs, triplets, out)


def _report(container, docs, triplets, out_path) -> None:
    extractor = container.build_knowledge_base.fact_extractor
    stats = getattr(extractor, "stats", {})
    dropped_examples = getattr(extractor, "dropped_examples", [])

    by_outcome = {"success": 0, "failure": 0, "neutral": 0}
    for t in triplets:
        by_outcome[t.outcome] = by_outcome.get(t.outcome, 0) + 1

    print("\n" + "=" * 56)
    print("ОТЧЁТ ОБ ИЗВЛЕЧЕНИИ")
    print("=" * 56)
    print(f"Документов:            {len(docs)}")
    print(f"Триплетов извлечено:   {len(triplets)}  →  {out_path}")
    if stats:
        print(f"  отброшено фильтром:  {stats.get('dropped', 0)}  (цитата не дословна / невалидно)")
        print(f"  вызовов API:         {stats.get('api_calls', 0)}")
        print(f"  чанков из кэша:      {stats.get('cached_chunks', 0)}")
    print(f"По исходам: success={by_outcome['success']} "
          f"failure={by_outcome['failure']} neutral={by_outcome['neutral']}")
    if dropped_examples:
        print("\nПримеры отброшенных (цитатный гейт сработал):")
        for ex in dropped_examples:
            print(f"  [{ex['chunk_id']}] {ex['reason']}")
            print(f"    цитата: {ex['quote']!r}")
    print("=" * 56)


if __name__ == "__main__":
    main()
