"""Генератор РАЗРЫВОВ (ABC Свонсона) — чистый домен.

Есть A→B и B→C, но прямого A→C нет → кандидат. Ограничено осмысленной типовой
цепочкой reagent→parameter→KPI. Доступ к графу — только через `GraphRepository`.
Детерминизм: тот же граф → тот же список в том же порядке.
"""

from __future__ import annotations

from app.service.domain.generation import _shared
from app.service.entities import Edge, ExperimentProtocol, Hypothesis, Node
from app.service.interfaces import GraphRepository

ORIGIN = "gap"


def generate(repo: GraphRepository, kpi: str | None) -> list[Hypothesis]:
    """Найти разрывы reagent→parameter→KPI, замкнутые на узле KPI."""
    if kpi is None:
        return []
    kpi_node = repo.get_node(kpi)
    if kpi_node is None or kpi_node.type != "KPI":
        return []

    seen: set[tuple[str, str]] = set()
    out: list[Hypothesis] = []
    # B→C (C = KPI), B — parameter
    for bc in sorted(repo.in_edges(kpi), key=lambda e: (e.source, e.year, e.doc_id)):
        b = repo.get_node(bc.source)
        if b is None or b.type != "parameter":
            continue
        # A→B, A — reagent
        for ab in sorted(repo.in_edges(b.id), key=lambda e: (e.source, e.year, e.doc_id)):
            a = repo.get_node(ab.source)
            if a is None or a.type != "reagent":
                continue
            key = (a.id, kpi_node.id)
            if key in seen:
                continue  # уже есть разрыв A→C по другому B — берём первый детерминированно
            # прямая связь A→C уже существует → это не разрыв
            if any(e.target == kpi_node.id for e in repo.out_edges(a.id)):
                continue
            seen.add(key)
            out.append(_build(a, b, kpi_node, ab, bc))
    return out


def _build(a: Node, b: Node, c: Node, ab: Edge, bc: Edge) -> Hypothesis:
    evidence = [ab, bc]
    return Hypothesis(
        id=f"h_gap__{a.id}__{c.id}",
        statement_if=f"воздействовать на «{c.label}» через «{a.label}»",
        statement_then=f"изменится «{c.label}»",
        statement_because=(
            f"«{a.label}» влияет на «{b.label}», а «{b.label}» — на «{c.label}», "
            f"но прямой связи «{a.label}»→«{c.label}» в графе нет (разрыв Свонсона)"
        ),
        origin=ORIGIN,
        evidence_path=evidence,
        experiment_protocol=ExperimentProtocol(
            method=f"Лабораторная проверка прямого влияния «{a.label}» на «{c.label}»",
            equipment="Лабораторная флотомашина, ICP-OES",
            duration_days=30,
            cost_rub=800_000,
        ),
        sources=_shared.sources_from_edges(evidence),
    )


__all__ = ["generate", "ORIGIN"]
