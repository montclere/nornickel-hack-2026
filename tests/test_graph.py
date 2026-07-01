"""Оффлайн-тесты сборки графа: нормализация (fake embedder), NetworkX-репозиторий, снапшот."""

from __future__ import annotations

import numpy as np
import pytest

from app.infrastructure.embeddings import EntityNormalizer
from app.service.entities import Edge, Node, Triplet
from app.service.pipeline import BuildGraph
from app.service.pipeline.build_graph import build_nodes_and_edges

pytest.importorskip("networkx")
from app.infrastructure.graph import NetworkxGraphRepository  # noqa: E402


class FakeEmbedder:
    """Детерминированный эмбеддер для тестов: имя → заранее заданный единичный вектор."""

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self.mapping = mapping

    def encode(self, texts):
        return np.array([self.mapping[t] for t in texts], dtype=float)


# --- нормализация по словарю ---


def test_dictionary_merges_cross_lingual_synonyms():
    norm = EntityNormalizer().normalize(
        ["Ni", "никель", "nickel", "извлечение Ni", "CMC", "carboxymethyl cellulose", "pulp pH"]
    )
    nof = norm.node_of
    assert nof["Ni"] == nof["никель"] == nof["nickel"] == "Ni"        # металл
    assert nof["извлечение Ni"] == "Ni_recovery"                       # KPI отдельно
    assert nof["CMC"] == nof["carboxymethyl cellulose"] == "CMC"       # реагент + англ. синоним
    assert nof["pulp pH"] == "pH"
    # у канонического узла копятся алиасы
    cmc = next(n for n in norm.nodes if n.id == "CMC")
    assert "carboxymethyl cellulose" in cmc.aliases and cmc.type == "reagent"


def test_normalize_is_deterministic():
    names = ["Ni", "никель", "CMC", "pulp pH", "неизвестный реагент X"]
    a = EntityNormalizer().normalize(names)
    b = EntityNormalizer().normalize(names)
    assert a.node_of == b.node_of
    assert [n.model_dump() for n in a.nodes] == [n.model_dump() for n in b.nodes]


def test_cosine_merges_unknowns_above_threshold():
    # alpha/alpha2 близки (cos≈0.95), beta далеко — словарь их не знает
    mapping = {
        "alpha widget": [1.0, 0.0],
        "alpha-widget": [0.95, np.sqrt(1 - 0.95**2)],
        "beta gadget": [0.0, 1.0],
    }
    norm = EntityNormalizer(embedder=FakeEmbedder(mapping), threshold=0.87).normalize(
        list(mapping)
    )
    nof = norm.node_of
    assert nof["alpha widget"] == nof["alpha-widget"]   # склеены по косинусу
    assert nof["beta gadget"] != nof["alpha widget"]    # далеко — отдельный узел


def test_cosine_respects_threshold():
    mapping = {"p one": [1.0, 0.0], "p two": [0.5, np.sqrt(1 - 0.25)]}  # cos=0.5 < 0.87
    norm = EntityNormalizer(embedder=FakeEmbedder(mapping), threshold=0.87).normalize(list(mapping))
    assert norm.node_of["p one"] != norm.node_of["p two"]


# --- NetworkX-репозиторий ---


def _repo_with_conflict() -> NetworkxGraphRepository:
    repo = NetworkxGraphRepository()
    repo.add_nodes([
        Node(id="pH", label="pH пульпы", type="parameter"),
        Node(id="Ni_recovery", label="Извлечение Ni", type="KPI"),
    ])
    repo.add_edges([
        Edge(source="pH", target="Ni_recovery", sign="+", doc_id="d2009",
             evidence_quote="growth", year=2009),
        Edge(source="pH", target="Ni_recovery", sign="-", doc_id="d2019",
             evidence_quote="loss", year=2019),
    ])
    return repo


def test_parallel_edges_and_conflicts_preserved():
    repo = _repo_with_conflict()
    assert len(repo.all_edges()) == 2            # параллельные рёбра разных лет сохранены
    conflicts = repo.conflicting_edges()
    assert len(conflicts) == 1
    a, b = conflicts[0]
    assert {a.sign, b.sign} == {"+", "-"}


def test_query_paths_and_neighbors():
    repo = _repo_with_conflict()
    repo.add_nodes([Node(id="CMC", label="CMC", type="reagent")])
    repo.add_edges([Edge(source="CMC", target="pH", sign="+", doc_id="d", evidence_quote="q", year=2015)])
    paths = repo.query_paths("CMC", "Ni_recovery", max_len=3)
    assert paths and all(p[0].source == "CMC" and p[-1].target == "Ni_recovery" for p in paths)
    assert {n.id for n in repo.neighbors("pH")} == {"CMC", "Ni_recovery"}


def test_failure_nodes_by_type():
    repo = NetworkxGraphRepository()
    repo.add_nodes([
        Node(id="failure_d1", label="Провал", type="failure", closure_reason="дорого"),
        Node(id="CMC", label="CMC", type="reagent"),
    ])
    failures = repo.failure_nodes()
    assert [n.id for n in failures] == ["failure_d1"]
    assert failures[0].closure_reason == "дорого"


def test_save_load_roundtrip(tmp_path):
    repo = _repo_with_conflict()
    path = tmp_path / "graph.json"
    repo.save(path)
    repo2 = NetworkxGraphRepository()
    repo2.load(path)
    assert [n.model_dump() for n in repo.all_nodes()] == [n.model_dump() for n in repo2.all_nodes()]
    assert sorted(e.model_dump().items().__str__() for e in repo.all_edges()) == \
           sorted(e.model_dump().items().__str__() for e in repo2.all_edges())


# --- BuildGraph: failure-узлы, снапшот, идемпотентность ---


def _sample_triplets() -> list[Triplet]:
    return [
        Triplet(id="t1", chunk_id="c", doc_id="rep_cmc", subject="CMC", relation="снижает",
                object="извлечение никеля", sign="-", outcome="failure",
                closure_reason="снижала извлечение никеля", evidence_quote="q1", year=2013),
        Triplet(id="t2", chunk_id="c", doc_id="d2009", subject="pH", relation="повышает",
                object="извлечение Ni", sign="+", outcome="neutral", evidence_quote="q2", year=2009),
        Triplet(id="t3", chunk_id="c", doc_id="d2019", subject="pH", relation="снижает",
                object="извлечение Ni", sign="-", outcome="neutral", evidence_quote="q3", year=2019),
    ]


def test_build_graph_creates_failure_node_and_conflict():
    triplets = _sample_triplets()
    repo = NetworkxGraphRepository()
    snap = BuildGraph(EntityNormalizer(), repo).execute(triplets)

    failures = repo.failure_nodes()
    assert any(f.id == "failure_rep_cmc" and f.closure_reason for f in failures)
    # CMC ведёт к узлу-провалу
    assert any(e.target == "failure_rep_cmc" for e in repo.out_edges("CMC"))
    # противоречие pH→Ni_recovery (+2009 / -2019) сохранилось
    assert len(repo.conflicting_edges()) == 1
    assert snap.triplet_count == 3 and len(snap.snapshot_id) == 16


def test_build_graph_is_idempotent_and_snapshot_stable():
    triplets = _sample_triplets()
    n1, e1 = build_nodes_and_edges(triplets, EntityNormalizer())
    n2, e2 = build_nodes_and_edges(list(reversed(triplets)), EntityNormalizer())
    # порядок входа не влияет на результат
    assert [n.model_dump() for n in n1] == [n.model_dump() for n in n2]
    repo_a, repo_b = NetworkxGraphRepository(), NetworkxGraphRepository()
    s1 = BuildGraph(EntityNormalizer(), repo_a).execute(triplets)
    s2 = BuildGraph(EntityNormalizer(), repo_b).execute(list(reversed(triplets)))
    assert s1.snapshot_id == s2.snapshot_id  # снапшот стабилен на одном входе
