"""Агент-разведчик на LangGraph: plan → act → observe → reflect → (loop|stop).

scout автономно ищет литературу, чтобы закрыть структурные пробелы вокруг KPI, и
добывает цитированные триплеты (цитатный гейт). Бюджет (шаги/запросы/время) и
критерий «покрытие перестало расти» гарантированно останавливают петлю. Единственный
персистентный эффект — валидированные Triplet; выбор гипотез остаётся в домене.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import TypedDict

from app.config import Settings, load_settings
from app.infrastructure.agent.llm import groq_complete
from app.infrastructure.agent.tools import extract_from_doc, find_gaps, search_literature
from app.infrastructure.sources.openalex import OpenAlexSource
from app.service.entities import AgentResult, AgentStep, AgentTrace, Mission, Triplet

logger = logging.getLogger(__name__)


class ScoutState(TypedDict, total=False):
    kpi: str
    gaps: list[dict]
    gap_idx: int
    query: str
    candidate: list  # Triplet, добытые на шаге act
    new_triplets: list  # Triplet, принятые (новые, не из графа)
    steps: list  # AgentStep — трейл
    added_last: int
    stagnation: int
    steps_used: int
    queries_used: int
    done: bool


class LangGraphResearchAgent:
    """ResearchAgent: mission="scout" (агент) + mission="chat" (read-only ответ)."""

    def __init__(
        self,
        *,
        graph_repository,
        extractor,
        source=None,
        settings: Settings | None = None,
        use_llm: bool = True,
        max_steps: int = 4,
        max_queries: int = 5,
        max_seconds: float = 45.0,
        max_stagnation: int = 2,
        search_limit: int = 4,
    ) -> None:
        self.repo = graph_repository
        self.extractor = extractor
        self.source = source or OpenAlexSource()
        self.settings = settings or load_settings()
        self.use_llm = use_llm and bool(os.getenv("GROQ_API_KEY"))
        self.max_steps = max_steps
        self.max_queries = max_queries
        self.max_seconds = max_seconds
        self.max_stagnation = max_stagnation
        self.search_limit = search_limit
        self._start = 0.0
        self._existing_docs: set[str] = set()
        self._seen: set[tuple] = set()

    # --- порт ---

    def run(self, mission: Mission, input: dict) -> AgentResult:
        if mission == "scout":
            return self._scout(input.get("kpi", ""))
        return self._chat(input.get("question", ""), input.get("kpi"))

    # --- scout: прогон LangGraph ---

    def _scout(self, kpi: str) -> AgentResult:
        self._start = time.monotonic()
        self._existing_docs = {e.doc_id for e in self.repo.all_edges()}
        self._seen = set()

        app = self._build_graph()
        final: ScoutState = app.invoke(
            {
                "kpi": kpi, "gaps": [], "gap_idx": 0, "query": "", "candidate": [],
                "new_triplets": [], "steps": [], "added_last": 0, "stagnation": 0,
                "steps_used": 0, "queries_used": 0, "done": False,
            },
            config={"recursion_limit": 60},
        )
        triplets: list[Triplet] = final.get("new_triplets", [])
        steps: list[AgentStep] = final.get("steps", [])
        return AgentResult(
            mission="scout",
            triplets=triplets,
            sources=sorted({t.doc_id for t in triplets}),
            trace=AgentTrace(id=f"trace_scout_{uuid.uuid4().hex[:8]}", mission="scout", steps=steps),
        )

    def _build_graph(self):
        from langgraph.graph import END, StateGraph  # ленивый импорт

        g = StateGraph(ScoutState)
        g.add_node("plan", self._plan)
        g.add_node("act", self._act)
        g.add_node("observe", self._observe)
        g.add_node("reflect", self._reflect)
        g.set_entry_point("plan")
        g.add_edge("plan", "act")
        g.add_edge("act", "observe")
        g.add_edge("observe", "reflect")
        g.add_conditional_edges("reflect", self._route, {"loop": "plan", "stop": END})
        return g.compile()

    # --- узлы графа состояний ---

    def _budget_left(self, state: ScoutState) -> bool:
        return (
            state["steps_used"] < self.max_steps
            and state["queries_used"] < self.max_queries
            and (time.monotonic() - self._start) < self.max_seconds
            and state["stagnation"] < self.max_stagnation
        )

    def _plan(self, state: ScoutState) -> dict:
        gaps = state["gaps"] or find_gaps(self.repo, state["kpi"])
        steps = list(state["steps"])
        if not self._budget_left(state) or state["gap_idx"] >= len(gaps):
            steps.append(AgentStep(
                thought="Бюджет исчерпан или пробелы кончились — останавливаюсь",
                tool="plan", query="",
            ))
            return {"gaps": gaps, "done": True, "steps": steps, "candidate": []}
        gap = gaps[state["gap_idx"]]
        query = self._plan_query(gap, state["kpi"])
        steps.append(AgentStep(
            thought=f"Пробел: «{gap['label']}» ({gap['type']}) не связан с KPI — ищу литературу",
            tool="plan", query=query,
        ))
        return {"gaps": gaps, "query": query, "steps": steps}

    def _act(self, state: ScoutState) -> dict:
        if state.get("done"):
            return {"candidate": []}
        steps = list(state["steps"])
        used = state["queries_used"] + 1
        # поиск литературы — отказ источника не валит весь прогон
        try:
            docs = search_literature(self.source, state["query"], limit=self.search_limit)
        except Exception as exc:  # noqa: BLE001 — сеть ненадёжна
            logger.warning("поиск упал: %s", exc)
            steps.append(AgentStep(thought=f"Источник недоступен ({type(exc).__name__}) — пропускаю",
                                   tool="search_literature", query=state["query"]))
            return {"candidate": [], "queries_used": used, "steps": steps}
        doc = next((d for d in docs if d.id not in self._existing_docs), None)
        if doc is None:
            steps.append(AgentStep(thought="По запросу ничего нового не нашлось",
                                   tool="search_literature", query=state["query"]))
            return {"candidate": [], "queries_used": used, "steps": steps}
        try:
            candidate = extract_from_doc(doc, self.extractor)
        except Exception as exc:  # noqa: BLE001 — извлечение ненадёжно
            logger.warning("извлечение упало: %s", exc)
            candidate = []
        quote = candidate[0].evidence_quote if candidate else None
        steps.append(AgentStep(
            thought=f"Источник: {doc.title[:70]} ({doc.year}) — извлёк {len(candidate)} фактов",
            tool="search_literature", query=state["query"],
            source_doc_id=doc.id, evidence_quote=quote,
        ))
        return {"candidate": candidate, "queries_used": used, "steps": steps}

    def _observe(self, state: ScoutState) -> dict:
        new = list(state["new_triplets"])
        added = 0
        for t in state.get("candidate", []):
            key = (t.doc_id, t.subject, t.object, t.sign)
            if t.doc_id in self._existing_docs or key in self._seen:
                continue
            self._seen.add(key)
            new.append(t)
            added += 1
        steps = list(state["steps"])
        steps.append(AgentStep(
            thought=f"Принято {added} новых цитированных фактов (всего {len(new)})",
            tool="observe", query="",
        ))
        return {"new_triplets": new, "added_last": added, "steps": steps}

    def _reflect(self, state: ScoutState) -> dict:
        grew = state.get("added_last", 0) > 0
        stagnation = 0 if grew else state["stagnation"] + 1
        steps_used = state["steps_used"] + 1
        gap_idx = state["gap_idx"] + 1
        done = (
            steps_used >= self.max_steps
            or stagnation >= self.max_stagnation
            or gap_idx >= len(state["gaps"])
            or state["queries_used"] >= self.max_queries
            or (time.monotonic() - self._start) >= self.max_seconds
        )
        steps = list(state["steps"])
        steps.append(AgentStep(
            thought=f"Рефлексия: покрытие {'выросло' if grew else 'не растёт'} "
                    f"(стагнация {stagnation}/{self.max_stagnation}); "
                    f"{'стоп' if done else 'продолжаю'}",
            tool="reflect", query="",
        ))
        return {"stagnation": stagnation, "steps_used": steps_used, "gap_idx": gap_idx,
                "done": done, "steps": steps}

    @staticmethod
    def _route(state: ScoutState) -> str:
        return "stop" if state.get("done") else "loop"

    def _plan_query(self, gap: dict, kpi: str) -> str:
        """Сформулировать поисковый запрос из пробела (LLM, иначе детерминированно)."""
        fallback = f"{gap['label']} nickel recovery flotation"
        if not self.use_llm:
            return fallback
        try:
            return groq_complete(
                f"Сущность: {gap['label']}. KPI: {kpi}.",
                system=(
                    "Сформулируй короткий англоязычный поисковый запрос (3–6 слов) для научной "
                    "литературы по флотации, чтобы связать сущность с KPI. Верни только запрос."
                ),
                max_tokens=40,
            ).splitlines()[0].strip().strip('"') or fallback
        except Exception as exc:  # noqa: BLE001 — сеть/ключ ненадёжны, не валим агента
            logger.warning("plan LLM упал, fallback-запрос: %s", exc)
            return fallback

    # --- chat: read-only ответ по графу ---

    def _chat(self, question: str, kpi: str | None) -> AgentResult:
        edges = [e for e in self.repo.all_edges() if e.evidence_quote][:40]
        context = "\n".join(
            f"- {e.source} {e.sign} {e.target} ({e.year}): «{e.evidence_quote}» [{e.doc_id}]"
            for e in edges
        )
        sources = sorted({e.doc_id for e in edges})[:6]
        step = AgentStep(
            thought="Ищу ответ в графе знаний", tool="query_graph", query=question,
            source_doc_id=sources[0] if sources else None,
        )
        if self.use_llm:
            try:
                answer = groq_complete(
                    f"Вопрос: {question}\n\nФакты из графа:\n{context}\n\n"
                    "Ответь кратко по-русски, опираясь ТОЛЬКО на эти факты, и упомяни источники.",
                    system="Ты отвечаешь по графу знаний флотации Cu-Ni руд, строго по фактам, со ссылками.",
                    max_tokens=350,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("chat LLM упал: %s", exc)
                answer = "Не удалось получить ответ от модели."
        else:
            answer = "Чат доступен в real-режиме с ключом Groq."
        return AgentResult(
            mission="chat", answer=answer, sources=sources,
            trace=AgentTrace(id=f"trace_chat_{uuid.uuid4().hex[:8]}", mission="chat", steps=[step]),
        )


__all__ = ["LangGraphResearchAgent"]
