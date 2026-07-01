"""Сборка корпуса знаний: OpenAlex + синтетические отчёты + сканы.

Запуск (из корня репозитория, нужна сеть для OpenAlex):

    python scripts/build_corpus.py                 # ~200 статей + отчёты + сканы
    python scripts/build_corpus.py --max-docs 120  # меньше статей
    python scripts/build_corpus.py --no-scans      # без рендера PDF-сканов

Пишет: data/corpus.jsonl, data/reports.jsonl, data/scans/*.pdf, data/charged_pairs.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import DATA_DIR, SCANS_DIR
from app.infrastructure.sources.openalex import OpenAlexSource
from app.infrastructure.sources.synthetic_reports import build_reports, render_scans
from app.service.entities import Document


def write_jsonl(path: Path, docs: list[Document]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(doc.model_dump_json() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Сборка корпуса «Феникс»")
    parser.add_argument("--max-docs", type=int, default=200, help="максимум статей OpenAlex")
    parser.add_argument("--mailto", default="phoenix-hackathon@example.com")
    parser.add_argument("--per-page", type=int, default=50)
    parser.add_argument("--no-scans", action="store_true", help="не рендерить PDF-сканы")
    args = parser.parse_args()

    # --- часть A: реальные статьи OpenAlex ---
    print("→ OpenAlex: загрузка статей…")
    source = OpenAlexSource(mailto=args.mailto, per_page=args.per_page)
    try:
        corpus = source.fetch(max_docs=args.max_docs)
    finally:
        source.close()
    corpus_path = DATA_DIR / "corpus.jsonl"
    write_jsonl(corpus_path, corpus)

    # --- часть B: синтетические отчёты + заряженные пары ---
    reports, charged_pairs = build_reports(corpus)
    report_docs = [r.to_document() for r in reports]

    scan_docs: list[Document] = []
    if not args.no_scans:
        print("→ рендер PDF-сканов…")
        scan_docs = render_scans(reports, SCANS_DIR)

    reports_path = DATA_DIR / "reports.jsonl"
    write_jsonl(reports_path, report_docs + scan_docs)

    pairs_path = DATA_DIR / "charged_pairs.json"
    pairs_path.write_text(json.dumps(charged_pairs, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_stats(corpus, reports, scan_docs, charged_pairs)


def _print_stats(corpus, reports, scan_docs, charged_pairs) -> None:
    failures = [r for r in reports if r.outcome == "failure"]
    successes = [r for r in reports if r.outcome == "success"]
    neutral = [r for r in reports if r.outcome == "neutral"]
    years = [d.year for d in corpus]

    print("\n" + "=" * 56)
    print("СТАТИСТИКА КОРПУСА «Феникс»")
    print("=" * 56)
    print(f"Статьи OpenAlex (data/corpus.jsonl):   {len(corpus)}")
    if years:
        print(f"  годы: {min(years)}–{max(years)}")
    print(f"Отчёты о НИР (data/reports.jsonl):     {len(reports)}")
    print(f"  провалы (с причиной закрытия):       {len(failures)}")
    print(f"  успехи:                              {len(successes)}")
    print(f"  нейтральные:                         {len(neutral)}")
    print(f"PDF-сканы (is_scanned, data/scans/):   {len(scan_docs)}")
    for d in scan_docs:
        print(f"    {d.id}  →  {d.source_path}")
    print(f"Заряженные пары (провал + свежий факт): {len(charged_pairs)}")
    for p in charged_pairs:
        print(f"    {p['failure_report_id']} [{p['reagent']}]")
        print(f"      ← снимает: {p['reviving_doc_id']} ({p['reviving_year']}) {p['reviving_title'][:64]}")
    print("=" * 56)

    ok = len(corpus) >= 100 and 15 <= len(reports) <= 20 and 8 <= len(failures) <= 10 and len(charged_pairs) >= 2
    print("Критерии готовности:", "ВЫПОЛНЕНЫ ✓" if ok else "НЕ ВЫПОЛНЕНЫ — проверьте сеть/корпус")


if __name__ == "__main__":
    main()
