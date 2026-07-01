"""Тесты API-слоя: полный сценарий через TestClient.

ingest → build_graph → research → generate → feedback, плюс chat/graph/trace.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from app.api import create_app  # noqa: E402

KPI = "извлечение Ni +2%"


@pytest.fixture
def client(tmp_path):
    app = create_app("fake", db_path=str(tmp_path / "phoenix.db"))
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "persistence" in body["adapter_modes"]


def test_full_scenario(client):
    # 1. приём корпуса (включая OCR-скан report_2012)
    r = client.post("/ingest", json={})
    assert r.status_code == 200 and r.json()["triplets"] >= 1

    # 2. граф + снапшот (идемпотентно)
    r = client.post("/build_graph", json={})
    assert r.status_code == 200
    snap1 = r.json()["snapshot_id"]
    assert r.json()["nodes"] > 0 and r.json()["edges"] > 0
    assert client.post("/build_graph", json={}).json()["snapshot_id"] == snap1  # кэш

    # 3. research: Scout дозаполняет, пишет трейл
    r = client.post("/research", json={"kpi": KPI})
    assert r.status_code == 200
    scout_trace = r.json()["trace_id"]
    assert client.get(f"/agent/trace/{scout_trace}").status_code == 200

    # 4. generate < 2 сек, ранжированные карточки всех типов
    t0 = time.perf_counter()
    r = client.post("/generate", json={"kpi": KPI})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    cards = r.json()
    assert cards and elapsed < 2.0
    assert {c["origin"] for c in cards} == {"gap", "reanimation", "contradiction"}
    hid = cards[0]["id"]

    # 5. цепочка доказательств для Cytoscape
    r = client.get(f"/graph/path/{hid}")
    assert r.status_code == 200
    els = r.json()["elements"]
    assert els["nodes"] and els["edges"]
    assert els["edges"][0]["data"]["quote"]  # клик → цитата

    # 6. фидбек → веса ранкера (персист)
    r = client.post(
        "/feedback",
        json={"hypothesis_id": hid, "decision": "reject", "reason": "дорого"},
    )
    assert r.status_code == 200 and isinstance(r.json(), dict)
    assert client.get("/ranker_weights").status_code == 200

    # 7. чат (read-only) со ссылками
    r = client.post("/chat", json={"question": "почему коллектор X отклонили в 2012?"})
    assert r.status_code == 200
    assert r.json()["answer"] and r.json()["sources"]


def test_full_graph(client):
    # полный граф (Connected-Papers-вид) доступен и до /generate
    r = client.get("/graph")
    assert r.status_code == 200
    els = r.json()["elements"]
    assert els["nodes"] and els["edges"]
    n0 = els["nodes"][0]["data"]
    assert {"id", "label", "type", "degree"} <= set(n0)  # degree → размер узла
    assert els["edges"][0]["data"]["quote"]  # клик по ребру → цитата


def test_graph_pyvis_html(client):
    pytest.importorskip("pyvis")
    r = client.get("/graph/pyvis")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "vis-network" in body  # инлайн vis.js (оффлайн-страница)
    assert "Ni_recovery" in body  # узлы графа попали в страницу (id в данных vis.js)


def test_unknown_ids_404(client):
    assert client.get("/graph/path/nope").status_code == 404
    assert client.get("/agent/trace/nope").status_code == 404
