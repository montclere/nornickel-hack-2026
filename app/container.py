"""Фабрика сборки приложения: собирает infrastructure и инжектит в use-cases.

`build(mode)` — единственная точка, где конкретные адаптеры подключаются к pipeline.
Каждый адаптер переключается НЕЗАВИСИМО через config (`PHOENIX_<C>=fake|real`):
напр. `PHOENIX_MODE=real PHOENIX_OCR=fake` — всё real, кроме OCR.

Состояние готовности адаптеров (на текущий момент проекта):
- real реализованы: extractor (Groq), phrasing (Claude), persistence (SQLite);
- ещё нет: ocr, embeddings/graph, agent — для них real откатывается на fake,
  поэтому build("real") остаётся оффлайн-запускаемым.

Адаптеры с онлайн-зависимостями уходят в real только при наличии своего ключа
(extractor → GROQ_API_KEY, phrasing → ANTHROPIC_API_KEY), иначе — fake. Реальный выбор
по каждому компоненту виден в `Container.adapter_modes`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib import util

from app.config import OUTPUTS_DIR, Mode, Settings, load_settings
from app.infrastructure.agent import LangGraphResearchAgent
from app.infrastructure.embeddings import EntityNormalizer, SbertEmbedding
from app.infrastructure.extraction import GroqFactExtractor
from app.infrastructure.fakes import (
    FakeCardPhrasing,
    FakeFactExtractor,
    FakeGraphRepository,
    FakeOcr,
    FakeResearchAgent,
)
from app.infrastructure.graph import NetworkxGraphRepository
from app.infrastructure.persistence import (
    SQLiteCorpusRepository,
    SQLiteFeedbackRepository,
    SQLiteRankerStateStore,
    connect,
)
from app.infrastructure.phrasing import ClaudeCardPhrasing
from app.service.interfaces import GraphRepository, ResearchAgent
from app.service.pipeline import (
    BuildGraph,
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
    build_graph_use_case: BuildGraph
    enrich_graph: EnrichGraph
    generate_hypotheses: GenerateHypotheses
    submit_feedback: SubmitFeedback
    chat: Chat
    corpus_repository: SQLiteCorpusRepository
    feedback_repository: SQLiteFeedbackRepository
    ranker_state_store: SQLiteRankerStateStore
    adapter_modes: dict[str, str] = field(default_factory=dict)


def build(mode: Mode = "fake", *, db_path: str | None = None) -> Container:
    """Собрать готовый к работе контейнер use-cases.

    mode="fake" — всё на фейках (оффлайн); "real"/"mix" — real там, где реализовано
    (phrasing/persistence), иначе fake; покомпонентно переключается через config.
    """
    settings = load_settings(mode=mode)
    modes: dict[str, str] = {}

    def pick(component, fake_factory, real_factory=None, *, key_env=None):
        """Выбрать адаптер по режиму компонента; вернуть инстанс и записать выбор.

        `key_env` — имя переменной с ключом онлайн-провайдера: если режим real, но
        ключа нет, мягко откатываемся на fake (демо не падает без ключей).
        """
        component_mode = settings.mode_for(component)
        if component_mode == "fake":
            modes[component] = "fake"
        elif real_factory is None:
            modes[component] = "fake (real ещё не готов)"
        elif key_env and not os.getenv(key_env):
            modes[component] = f"fake (нет {key_env})"
        else:
            modes[component] = "real"
        return real_factory() if modes[component] == "real" else fake_factory()

    ocr = pick("ocr", FakeOcr)  # real: Unlimited-OCR
    fact_extractor = pick(
        "extractor", FakeFactExtractor,
        lambda: GroqFactExtractor(settings=settings), key_env="GROQ_API_KEY",
    )
    graph_repository = pick("graph", FakeGraphRepository, NetworkxGraphRepository)
    research_agent = pick(
        "agent", FakeResearchAgent,
        lambda: LangGraphResearchAgent(
            graph_repository=graph_repository, extractor=fact_extractor, settings=settings
        ),
        key_env="GROQ_API_KEY",
    )
    card_phrasing = pick(
        "phrasing", FakeCardPhrasing, lambda: ClaudeCardPhrasing(settings=settings),
        key_env="ANTHROPIC_API_KEY",
    )

    # нормализация синонимов: real → sbert-косинус поверх словаря, fake → только словарь.
    # Если sentence-transformers не установлен — мягкий откат на словарь (без косинуса).
    if settings.mode_for("embeddings") != "fake" and util.find_spec("sentence_transformers"):
        embedder = SbertEmbedding(settings=settings)
        modes["embeddings"] = "real (sbert)"
    else:
        embedder = None
        modes["embeddings"] = (
            "fake (словарь без косинуса)"
            if settings.mode_for("embeddings") == "fake"
            else "fake (sentence-transformers не установлен)"
        )
    normalizer = EntityNormalizer(embedder=embedder, settings=settings)

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
        build_graph_use_case=BuildGraph(normalizer, graph_repository),
        enrich_graph=EnrichGraph(research_agent, graph_repository, normalizer),
        generate_hypotheses=GenerateHypotheses(graph_repository, card_phrasing),
        submit_feedback=SubmitFeedback(ranker_store),
        chat=Chat(research_agent, graph_repository),
        corpus_repository=corpus_repo,
        feedback_repository=feedback_repo,
        ranker_state_store=ranker_store,
        adapter_modes=modes,
    )


__all__ = ["Container", "build"]
