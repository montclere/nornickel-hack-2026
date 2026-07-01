"""Сборка карточки-гипотезы + постпроверка «никаких новых сущностей» — чистый домен.

`pattern_fields` извлекает из гипотезы структурированные поля для CardPhrasing (порт);
`assemble` принимает оформленный текст и собирает финальную Hypothesis — но только если
текст не ввёл сущностей вне evidence_path. При нарушении домен оставляет детерминированный
текст-baseline (от генератора) и помечает карточку `phrasing_flag`. Так LLM физически не
может протащить факт, которого нет в графе.
"""

from __future__ import annotations

import re

from app.service.domain import graph_ops
from app.service.entities import Hypothesis, Node, PhrasedCard
from app.service.interfaces import GraphRepository


def _label(repo: GraphRepository, node_id: str | None) -> str:
    if node_id is None:
        return ""
    node = repo.get_node(node_id)
    return node.label if node is not None else node_id


def _node_terms(node: Node) -> set[str]:
    """Все опознавательные термины узла (id/label/aliases), нормализованные."""
    terms = {node.id.lower(), node.label.lower(), *(a.lower() for a in node.aliases)}
    return {t for t in terms if len(t) >= 2}


def _mentions(text: str, term: str) -> bool:
    """Term встречается в тексте как отдельное слово/фраза (границы по \\w)."""
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


def _allowed_node_ids(hypothesis: Hypothesis, repo: GraphRepository, kpi: str | None) -> set[str]:
    """Узлы, которые карточке разрешено упоминать: из evidence_path + сам KPI."""
    allowed = {e.source for e in hypothesis.evidence_path}
    allowed |= {e.target for e in hypothesis.evidence_path}
    kpi_id = graph_ops.resolve_kpi_node(repo, kpi) if kpi else None
    if kpi_id:
        allowed.add(kpi_id)
    return allowed


def pattern_fields(
    hypothesis: Hypothesis, repo: GraphRepository, kpi: str | None = None
) -> dict:
    """Структурированные поля для CardPhrasing (LLM их только переформулирует)."""
    kpi_id = graph_ops.resolve_kpi_node(repo, kpi) if kpi else None
    evidence = hypothesis.evidence_path
    subject_id = evidence[0].source if evidence else None
    target_id = kpi_id or (evidence[-1].target if evidence else None)

    allowed = _allowed_node_ids(hypothesis, repo, kpi)
    allowed_entities = sorted(_label(repo, nid) for nid in allowed)
    conditions: dict = {}
    for edge in evidence:
        conditions.update(edge.conditions)

    return {
        "origin": hypothesis.origin,
        "intervention": _label(repo, subject_id),
        "effect_target": _label(repo, target_id),
        "kpi": _label(repo, kpi_id) if kpi_id else None,
        "mechanism": hypothesis.statement_because,
        "allowed_entities": allowed_entities,
        "conditions": conditions,
        "evidence": [
            {
                "from": _label(repo, e.source),
                "to": _label(repo, e.target),
                "sign": e.sign,
                "year": e.year,
                "doc_id": e.doc_id,
                "quote": e.evidence_quote,
            }
            for e in evidence
        ],
        # детерминированный baseline-текст генератора (заземлён в графе) —
        # fallback и эталон, который LLM лишь переоформляет
        "baseline": {
            "if": hypothesis.statement_if,
            "then": hypothesis.statement_then,
            "because": hypothesis.statement_because,
        },
    }


def verify_no_new_entities(
    text: str, hypothesis: Hypothesis, repo: GraphRepository, kpi: str | None = None
) -> list[str]:
    """Вернуть метки узлов графа, упомянутых в тексте, но отсутствующих в evidence (+KPI)."""
    allowed = _allowed_node_ids(hypothesis, repo, kpi)
    low = text.lower()
    offenders: set[str] = set()
    for node in repo.all_nodes():
        if node.id in allowed:
            continue
        if any(_mentions(low, term) for term in _node_terms(node)):
            offenders.add(node.label)
    return sorted(offenders)


def assemble(
    hypothesis: Hypothesis,
    phrased: PhrasedCard,
    repo: GraphRepository,
    kpi: str | None = None,
) -> Hypothesis:
    """Применить оформленный текст к гипотезе после постпроверки сущностей.

    Чисто: при нарушении возвращает гипотезу с детерминированным текстом-baseline
    и заполненным `phrasing_flag` — галлюцинированный текст наружу не уходит.
    """
    text = " ".join([phrased.if_, phrased.then, phrased.because])
    offenders = verify_no_new_entities(text, hypothesis, repo, kpi)
    if offenders:
        return hypothesis.model_copy(
            update={"phrasing_flag": f"новые сущности вне evidence_path: {offenders}"}
        )
    return hypothesis.model_copy(
        update={
            "statement_if": phrased.if_,
            "statement_then": phrased.then,
            "statement_because": phrased.because,
            "phrasing_flag": None,
        }
    )


__all__ = ["pattern_fields", "verify_no_new_entities", "assemble"]
