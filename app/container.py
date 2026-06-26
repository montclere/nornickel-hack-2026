"""Фабрика сборки приложения: собирает infrastructure и инжектит в use-cases.

`build(mode)` — единственная точка, где конкретные адаптеры подключаются к pipeline.
Каждый адаптер переключается НЕЗАВИСИМО через config (`PHOENIX_<C>=fake|real`):
напр. `PHOENIX_MODE=real PHOENIX_OCR=fake` — всё real, кроме OCR.

Состояние готовности адаптеров (на текущий момент проекта):
- real реализованы: phrasing (Claude), persistence (SQLite);
- ещё нет: ocr (1b), extractor (2), embeddings/graph (3), agent (3b) — для них real
  откатывается на fake, поэтому build("real") остаётся оффлайн-запускаемым.

Адаптеры с онлайн-зависимостями (phrasing → Claude API) уходят в real только при наличии
ANTHROPIC_API_KEY, иначе — fake. Реальный выбор по каждому компоненту виден в
`Container.adapter_modes`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.config import OUTPUTS_DIR, Mode, Settings, load_settings
from app.infrastructure.fakes import (
    FakeCardPhrasing,
    FakeFactExtractor,
    FakeGraphRepository,
    FakeOcr,
    FakeResearchAgent,
)
from app.infrastructure.persistence import (
    SQLiteCorpusRepository,
    SQLiteFeedbackRepository,
    SQLiteRankerStateStore,
    connect,
)
from app.infrastructure.phrasing import ClaudeCardPhrasing
from app.service.interfaces import GraphRepository, ResearchAgent
from app.service.pipeline import (
    BuildKnowledgeBase,
    Chat,
    EnrichGraph,
    GenerateHypotheses,
    SubmitFeedback,
)


@dataclass
class Container:
    """Собранные зависимости и готовые use-cases."""

    settings: Settings
    graph_repository: GraphRepository
    research_agent: ResearchAgent
    build_knowledge_base: BuildKnowledgeBase
    enrich_graph: EnrichGraph
    generate_hypotheses: GenerateHypotheses
    submit_feedback: SubmitFeedback
    chat: Chat
    corpus_repository: SQLiteCorpusRepository
    feedback_repository: SQLiteFeedbackRepository
    ranker_state_store: SQLiteRankerStateStore
    adapter_modes: dict[str, str] = field(default_factory=dict)


def _key_present() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def build(mode: Mode = "fake", *, db_path: str | None = None) -> Container:
    """Собрать готовый к работе контейнер use-cases.

    mode="fake" — всё на фейках (оффлайн); "real"/"mix" — real там, где реализовано
    (phrasing/persistence), иначе fake; покомпонентно переключается через config.
    """
    settings = load_settings(mode=mode)
    modes: dict[str, str] = {}

    def pick(component, fake_factory, real_factory=None, *, online=False):
        """Выбрать адаптер по режиму компонента; вернуть инстанс и записать выбор."""
        component_mode = settings.mode_for(component)
        if component_mode == "fake":
            modes[component] = "fake"
        elif real_factory is None:
            modes[component] = "fake (real ещё не готов)"
        elif online and not _key_present():
            modes[component] = "fake (нет ANTHROPIC_API_KEY)"
        else:
            modes[component] = "real"
        return real_factory() if modes[component] == "real" else fake_factory()

    ocr = pick("ocr", FakeOcr)  # real: Unlimited-OCR
    fact_extractor = pick("extractor", FakeFactExtractor)  # real: Claude
    graph_repository = pick("graph", FakeGraphRepository)  # real: NetworkX
    research_agent = pick("agent", FakeResearchAgent)  # real: LangGraph
    card_phrasing = pick(
        "phrasing", FakeCardPhrasing, lambda: ClaudeCardPhrasing(settings=settings),
        online=True,
    )

    # персист — всегда SQLite (оффлайн, stdlib). fake → :memory:, real → файл.
    if db_path is None:
        db_path = ":memory:" if mode == "fake" else str(OUTPUTS_DIR / "phoenix.db")
    conn = connect(db_path)
    corpus_repo = SQLiteCorpusRepository(conn)
    feedback_repo = SQLiteFeedbackRepository(conn)
    ranker_store = SQLiteRankerStateStore(conn)
    modes["persistence"] = f"SQLite ({db_path})"

    return Container(
        settings=settings,
        graph_repository=graph_repository,
        research_agent=research_agent,
        build_knowledge_base=BuildKnowledgeBase(ocr, fact_extractor),
        enrich_graph=EnrichGraph(research_agent, graph_repository),
        generate_hypotheses=GenerateHypotheses(graph_repository, card_phrasing),
        submit_feedback=SubmitFeedback(ranker_store),
        chat=Chat(research_agent, graph_repository),
        corpus_repository=corpus_repo,
        feedback_repository=feedback_repo,
        ranker_state_store=ranker_store,
        adapter_modes=modes,
    )


__all__ = ["Container", "build"]
