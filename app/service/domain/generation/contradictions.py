"""Генератор ПРОТИВОРЕЧИЙ — чистый домен.

Пары рёбер A→B с противоположным sign из разных лет → «эффект A на B зависит от
условия C» (C — различающееся condition, если есть). Скрытая переменная.
"""

from __future__ import annotations

from app.service.domain.generation import _shared
from app.service.entities import Edge, ExperimentProtocol, Hypothesis
from app.service.interfaces import GraphRepository

ORIGIN = "contradiction"


def generate(repo: GraphRepository, kpi: str | None = None) -> list[Hypothesis]:
    out: list[Hypothesis] = []
    seen: set[tuple[str, str, int, int]] = set()
    for a, b in repo.conflicting_edges():
        if a.year == b.year:
            continue  # противоречие именно «из разных лет»
        e1, e2 = sorted((a, b), key=lambda e: (e.year, e.sign, e.doc_id))
        key = (e1.source, e1.target, e1.year, e2.year)
        if key in seen:
            continue
        seen.add(key)
        out.append(_build(repo, e1, e2))
    out.sort(key=lambda h: h.id)
    return out


def _differing_condition(e1: Edge, e2: Edge) -> str | None:
    """Первый ключ условия, по которому рёбра расходятся (различающаяся переменная C)."""
    for key in sorted(set(e1.conditions) | set(e2.conditions)):
        if e1.conditions.get(key) != e2.conditions.get(key):
            return key
    return None


def _build(repo: GraphRepository, e1: Edge, e2: Edge) -> Hypothesis:
    a_label = _shared.label(repo, e1.source)
    b_label = _shared.label(repo, e1.target)
    cond = _differing_condition(e1, e2)
    cond_txt = f"«{cond}»" if cond else "скрытое условие"
    evidence = [e1, e2]
    return Hypothesis(
        id=f"h_contra__{e1.source}__{e1.target}",
        statement_if=f"проверить эффект «{a_label}» на «{b_label}» при разных значениях {cond_txt}",
        statement_then=(
            f"определится условие, от которого зависит знак влияния «{a_label}» на «{b_label}»"
        ),
        statement_because=(
            f"в {e1.year} знак влияния был «{e1.sign}», а в {e2.year} — «{e2.sign}»; "
            f"противоречие указывает на скрытую переменную {cond_txt}"
        ),
        origin=ORIGIN,
        evidence_path=evidence,
        experiment_protocol=ExperimentProtocol(
            method=(
                f"Факторный эксперимент: влияние «{a_label}» на «{b_label}» "
                f"при варьировании условия {cond_txt}"
            ),
            equipment="Лабораторная флотомашина, контроль условий",
            duration_days=60,
            cost_rub=1_200_000,
        ),
        sources=_shared.sources_from_edges(evidence),
    )


__all__ = ["generate", "ORIGIN"]
