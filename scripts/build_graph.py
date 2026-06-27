"""Сборка графа знаний из triplets.jsonl → data/graph.json + снапшот.

Нормализует сущности (словарь + опц. sbert-косинус), строит узлы/рёбра, выделяет
провалы отдельным типом, замораживает snapshot_id и сохраняет граф. Печатает пример
склейки синонимов (до/после) и проверяет идемпотентность повторной сборки.

Запуск:  python scripts/build_graph.py
"""

from __future__ import annotations

import json
import sys

from app.config import DATA_DIR
from app.infrastructure.embeddings import EntityNormalizer, SbertEmbedding
from app.infrastructure.graph import NetworkxGraphRepository
from app.service.entities import Triplet
from app.service.pipeline import BuildGraph


def main() -> None:
    src = DATA_DIR / "triplets.jsonl"
    if not src.exists():
        sys.exit(f"Нет {src}. Сначала: python scripts/extract_facts.py")
    triplets = [Triplet(**json.loads(line)) for line in src.read_text(encoding="utf-8").splitlines()]

    # sbert если установлен (косинусная склейка), иначе только словарь
    try:
        import sentence_transformers  # noqa: F401

        embedder, emb_mode = SbertEmbedding(), "sbert + словарь"
    except ImportError:
        embedder, emb_mode = None, "только словарь (sbert не установлен)"
    normalizer = EntityNormalizer(embedder=embedder)

    repo = NetworkxGraphRepository()
    snapshot = BuildGraph(normalizer, repo).execute(triplets)
    repo.save(DATA_DIR / "graph.json")
    (DATA_DIR / "snapshot.json").write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")

    # идемпотентность: повторная сборка в свежий репозиторий должна совпасть
    repo2 = NetworkxGraphRepository()
    BuildGraph(normalizer, repo2).execute(triplets)
    identical = [n.model_dump() for n in repo.all_nodes()] == [n.model_dump() for n in repo2.all_nodes()] \
        and [e.model_dump() for e in repo.all_edges()] == [e.model_dump() for e in repo2.all_edges()]

    _report(repo, snapshot, triplets, emb_mode, identical)


def _report(repo, snapshot, triplets, emb_mode, identical) -> None:
    nodes = repo.all_nodes()
    failures = repo.failure_nodes()
    conflicts = repo.conflicting_edges()
    merged = sorted((n for n in nodes if n.aliases), key=lambda n: -len(n.aliases))

    print("\n" + "=" * 60)
    print("ГРАФ ЗНАНИЙ СОБРАН")
    print("=" * 60)
    print(f"Нормализация:     {emb_mode}")
    print(f"Триплетов:        {len(triplets)}")
    print(f"Узлов:            {len(nodes)}  (провалов type=failure: {len(failures)})")
    print(f"Рёбер:            {len(repo.all_edges())}")
    print(f"Противоречий:     {len(conflicts)}  (параллельные рёбра разных лет)")
    print(f"snapshot_id:      {snapshot.snapshot_id}")
    print(f"Повторная сборка идентична: {'да' if identical else 'НЕТ'}")
    print(f"Сохранено: {DATA_DIR/'graph.json'}, {DATA_DIR/'snapshot.json'}")

    print("\nСклейка синонимов (до → после):")
    for n in merged[:8]:
        variants = ", ".join(sorted({n.label, *n.aliases}))
        print(f"  [{n.id}] ({n.type}): {variants}")

    if failures:
        print("\nПровалы (кладбище):")
        for f in failures[:6]:
            print(f"  {f.id}: {f.closure_reason}")
    print("=" * 60)


if __name__ == "__main__":
    main()
