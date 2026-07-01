"""Все доменные сущности проекта «Феникс» (pydantic v2).

Это единственный источник истины по форме данных. Все слои (api/service/infra)
обмениваются именно этими моделями; fixtures/*.json — валидируемые примеры каждой.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --- типы-перечисления (Literal — чтобы валидация ловила опечатки) -----------

Sign = Literal["+", "-", "0"]
Outcome = Literal["success", "failure", "neutral"]
NodeType = Literal["material", "reagent", "parameter", "process", "KPI", "failure"]
Origin = Literal["gap", "reanimation", "contradiction"]
Decision = Literal["accept", "reject", "edit"]
Mission = Literal["scout", "chat"]
DocSource = Literal["openalex", "report"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- приём документов ---------------------------------------------------------


class Document(BaseModel):
    """Документ корпуса: реальная статья (OpenAlex) либо синтетический отчёт о НИР."""

    id: str
    title: str
    year: int
    source: DocSource
    url: str | None = None
    is_synthetic: bool = False
    is_scanned: bool = False
    text: str | None = None
    source_path: str | None = None


class ParsedDocument(BaseModel):
    """Выход OCR (или текстового fast-path): документ, разобранный в markdown."""

    doc_id: str
    markdown: str
    pages: list[str] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class Chunk(BaseModel):
    """Фрагмент документа после нарезки — вход для извлечения фактов."""

    id: str
    doc_id: str
    text: str
    position: int


# --- факты и граф знаний ------------------------------------------------------


class Triplet(BaseModel):
    """Извлечённый факт: (subject, relation, object) со знаком, условиями и цитатой.

    Триплет без `evidence_quote`, присутствующей в исходном фрагменте дословно,
    отбраковывается на этапе извлечения (фильтр галлюцинаций).
    """

    id: str
    chunk_id: str
    doc_id: str
    subject: str
    relation: str
    object: str
    sign: Sign
    conditions: dict = Field(default_factory=dict)
    outcome: Outcome = "neutral"
    closure_reason: str | None = None
    evidence_quote: str
    year: int


class Node(BaseModel):
    """Узел графа знаний. Провалы — отдельный тип `failure` с `closure_reason`."""

    id: str  # канонический id после нормализации синонимов
    label: str
    type: NodeType
    aliases: list[str] = Field(default_factory=list)
    closure_reason: str | None = None


class Edge(BaseModel):
    """Направленное влияние со знаком, условиями и ссылкой на первоисточник.

    Параллельные рёбра разных лет сохраняются — на них держится генератор противоречий.
    """

    source: str
    target: str
    sign: Sign
    conditions: dict = Field(default_factory=dict)
    doc_id: str
    evidence_quote: str
    year: int


# --- гипотезы -----------------------------------------------------------------


class GraveyardCheck(BaseModel):
    """Результат фильтра «анти-грабли»: сверка кандидата с кладбищем провалов."""

    warning: bool = False
    report_ref: str | None = None
    reason: str | None = None
    difference: str | None = None  # чем гипотеза отличается от провального направления


class ExperimentProtocol(BaseModel):
    """Протокол минимального эксперимента для проверки гипотезы."""

    method: str
    equipment: str
    duration_days: int
    cost_rub: int


class MetricBreakdown(BaseModel):
    """Оценка одной метрики: итоговое число [0,1] + разложение по вкладам для UI."""

    value: float
    components: dict[str, float] = Field(default_factory=dict)


class Hypothesis(BaseModel):
    """Карточка-гипотеза «ЕСЛИ — ТО — ПОТОМУ ЧТО» с цепочкой доказательств и оценками."""

    id: str
    statement_if: str
    statement_then: str
    statement_because: str
    origin: Origin
    evidence_path: list[Edge] = Field(default_factory=list)
    novelty: float = 0.0
    risk: float = 0.0
    value: float = 0.0
    rank_score: float | None = None
    # разложение метрик и вклад признаков в ранг (интерпретируемость)
    novelty_breakdown: MetricBreakdown | None = None
    risk_breakdown: MetricBreakdown | None = None
    value_breakdown: MetricBreakdown | None = None
    rank_contributions: dict[str, float] = Field(default_factory=dict)
    # выставляется доменом, если CardPhrasing ввёл сущность вне evidence_path
    phrasing_flag: str | None = None
    graveyard_check: GraveyardCheck = Field(default_factory=GraveyardCheck)
    experiment_protocol: ExperimentProtocol
    sources: list[str] = Field(default_factory=list)


class PhrasedCard(BaseModel):
    """Выход CardPhrasing — оформленные тексты {if, then, because}.

    `if` — зарезервированное слово, поэтому поле зовётся `if_` с алиасом `if`
    (populate_by_name=True позволяет создавать и по имени поля, и по алиасу).
    """

    model_config = ConfigDict(populate_by_name=True)

    if_: str = Field(alias="if")
    then: str
    because: str


# --- обратная связь эксперта и ранжирование ----------------------------------


class Feedback(BaseModel):
    """Решение эксперта по карточке: принять/отклонить/править с причиной."""

    hypothesis_id: str
    decision: Decision
    reason: str
    timestamp: datetime = Field(default_factory=_utcnow)


# --- агент и снапшот графа ----------------------------------------------------


class AgentStep(BaseModel):
    """Шаг агента в трейле: мысль → инструмент → запрос → источник → цитата."""

    thought: str
    tool: str
    query: str
    source_doc_id: str | None = None
    evidence_quote: str | None = None


class AgentTrace(BaseModel):
    """Трейл прогона агента (виден в UI для прозрачности)."""

    id: str
    mission: Mission
    steps: list[AgentStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class AgentResult(BaseModel):
    """Результат ResearchAgent.run.

    mission="scout" → новые цитированные `triplets` + `trace`;
    mission="chat"  → `answer` + `sources` (ссылки на первоисточники) + `trace`.
    """

    mission: Mission
    triplets: list[Triplet] = Field(default_factory=list)
    answer: str | None = None
    sources: list[str] = Field(default_factory=list)
    trace: AgentTrace


class GraphSnapshot(BaseModel):
    """Замороженный снапшот графа: `snapshot_id` = хеш отсортированных триплетов."""

    snapshot_id: str
    triplet_count: int
    created_at: datetime = Field(default_factory=_utcnow)


__all__ = [
    "Document",
    "ParsedDocument",
    "Chunk",
    "Triplet",
    "Node",
    "Edge",
    "GraveyardCheck",
    "ExperimentProtocol",
    "MetricBreakdown",
    "Hypothesis",
    "PhrasedCard",
    "Feedback",
    "AgentStep",
    "AgentTrace",
    "AgentResult",
    "GraphSnapshot",
]
