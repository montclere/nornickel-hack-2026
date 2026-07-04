# -*- coding: utf-8 -*-
"""Генерация гипотез из канонического графа. ДЕТЕРМИНИРОВАННО поверх извлечённых связей.

Стратегии (без LLM в логике):
  gaps      — разрывы Свонсона: A→B и B→C есть, прямого A→C нет → скрытая связь;
  novelty   — редкость: чем меньше связность концов, тем новее (структурная новизна).
Ранжирование прозрачно: novelty · relevance · (знак-согласованность) · action-бонус.

is_action (проставлен в extract.py по классификации LLM, ПРОВЕРЯЕТСЯ не здесь, а там —
цитатным гейтом на исходный факт) — является ли рычаг (A) конкретным промышленным
действием (оборудование/реагент/режим), а не абстрактным научным свойством. Такие
гипотезы получают бонус к рангу и формулируются как рекомендация «внедрить», а не как
нейтральное «исследовать влияние» — это и есть смещение генерации в сторону
промышленных действий, а не абстракций, при том же цитатном заземлении.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache


@lru_cache(maxsize=None)
def _tokens(s):
    return frozenset(re.findall(r"[а-яёa-z]{4,}", (s or "").lower()))


@lru_cache(maxsize=None)
def _sim(a, b):
    """Похожесть узлов по токенам. Кэшируется: find_gaps сравнивает пары O(E²) раз."""
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0


@dataclass
class Discovery:
    a: str
    b: str
    c: str
    sign: int
    chain: list                      # [(edge_data), (edge_data)]
    novelty: float = 0.0
    relevance: float = 0.0
    is_action: bool = False          # A — промышленное действие, а не абстрактный факт
    role: str = "reference"          # "state" (факт про ЭТУ фабрику) vs "reference" (общая теория)
    score: float = 0.0
    statement_if: str = ""
    statement_then: str = ""
    statement_because: str = ""
    sources: list = field(default_factory=list)


def find_gaps(kg, thr=0.5):
    """A→B, B→C есть, прямого A→C нет (нечёткий матч сущностей).

    Раньше здесь был вложенный `any(...)` по ВСЕМ рёбрам внутри двойного цикла — это
    O(E³) и на большом корпусе взрывалось. Убрано: (a,c) не должно быть прямым ребром
    (O(1) проверка), а близость к уже существующим связям теперь гасится метрикой
    новизны при ранжировании (см. score) — там же, где ей и место."""
    edges = [(u, v, d) for u, v, d in kg.g.edges(data=True)]
    direct = {(u, v) for u, v, _ in edges}
    out, seen = [], set()
    for a, b, d1 in edges:
        for b2, c, d2 in edges:
            if _sim(b, b2) < thr or _sim(a, c) >= thr:
                continue
            if (a, c) in direct or (a, c) in seen:
                continue
            seen.add((a, c))
            sign = 1 if d1.get("sign", 0) * d2.get("sign", 0) >= 0 else -1
            out.append((a, b, c, sign, [d1, d2]))
    return out


def _corpus_df(kg):
    """Частота токенов по узлам графа (document frequency) — для оценки редкости."""
    df = {}
    for n in kg.g.nodes():
        for t in _tokens(kg.label(n)):
            df[t] = df.get(t, 0) + 1
    return df, (kg.g.number_of_nodes() or 1)


def _novelty(a_label, c_label, df, n_nodes):
    """Новизна как РЕДКОСТЬ концептов связи в корпусе (idf-подобно): редкие сущности =
    меньше представлены в имеющемся знании = новее. Это прокси к определению новизны из
    QA («отличие от существующих составов в базе»): когда появится внешняя база готовых
    решений, сюда подставляется непохожесть на неё; пока меряем редкость внутри корпуса,
    что честнее прежней «разреженности графа по степеням вершин»."""
    toks = _tokens(a_label) | _tokens(c_label)
    if not toks:
        return 0.0
    return round(sum(1 - df.get(t, 0) / n_nodes for t in toks) / len(toks), 3)


def find_direct(kg, kpi_tokens, thr=1):
    """Прямые рычаги: связь, релевантная KPI → гипотеза «влиять на цель через X».
    Релевантность ищем в объекте, субъекте И цитате (не только в объекте) — иначе
    короткий KPI не пересекается лексически ни с чем. Работает на разреженном графе."""
    out, seen = [], set()
    for u, v, d in kg.g.edges(data=True):
        hay = _tokens(v) | _tokens(u) | _tokens(d.get("quote", ""))
        if len(hay & kpi_tokens) < thr:
            continue
        if (u, v) in seen:
            continue
        seen.add((u, v))
        out.append((u, kg.label(v), v, d.get("sign", 0), [d]))
    return out


def _all_as_direct(kg):
    """Все связи как прямые кандидаты (fallback, когда KPI лексически не пересёкся)."""
    return [(u, kg.label(v), v, d.get("sign", 0), [d]) for u, v, d in kg.g.edges(data=True)]


# не-действие → штраф, чтобы промышленные рычаги систематически ранжировались выше
# абстрактных научных фактов при сходных novelty/relevance (не скрываем последние —
# просто честно отодвигаем и иначе формулируем, см. ниже)
_NON_ACTION_PENALTY = 0.6
# факт про ЭТУ фабрику (role="state") — точнее общей теории, скромный бонус к рангу.
# Сегодня почти все источники — "reference" (книги в materials/knowledge/), эффект
# проявится, когда в materials появится проза про конкретную фабрику (см. ingest.py)
_STATE_BONUS = 1.15


def score(kg, cands, kpi_tokens=None, kind="gap"):
    kpi_tokens = kpi_tokens or set()
    df, n_nodes = _corpus_df(kg)                 # один проход O(E) на корпус, дальше O(1)
    res = []
    for a, b, c, sign, chain in cands:
        novelty = _novelty(kg.label(a), kg.label(c), df, n_nodes)
        relevance = round(len(_tokens(c) & kpi_tokens) / (len(kpi_tokens) or 1), 3) \
            if kpi_tokens else 0.5
        # действие/роль рычага (A) — берём из ПЕРВОГО ребра цепочки, у него subject == A
        is_action = bool(chain[0].get("is_action", False))
        role = chain[0].get("role", "reference")
        base = novelty * (0.4 + 0.6 * (relevance or 0.2))
        base = base if is_action else base * _NON_ACTION_PENALTY
        base = base * _STATE_BONUS if role == "state" else base
        d = Discovery(a=kg.label(a), b=kg.label(b) if kind == "gap" else "",
                      c=kg.label(c), sign=sign, chain=chain,
                      novelty=novelty, relevance=relevance, is_action=is_action, role=role,
                      score=round(base, 4),
                      sources=sorted({e.get("locator", "") for e in chain}))
        verb = "повысит" if sign > 0 else "снизит" if sign < 0 else "изменит"
        if is_action:
            # промышленное действие — формулируем как рекомендацию к внедрению
            d.statement_if = f"внедрить/применить «{d.a}» (целевой параметр «{d.c}»)"
            d.statement_then = f"{verb} «{d.c}»"
        else:
            # абстрактный научный факт — честно НЕ выдаём за готовое действие
            d.statement_if = f"исследовать применимость к фабрике: «{d.a}» → «{d.c}»"
            d.statement_then = (f"фактор, потенциально влияющий на «{d.c}» "
                                f"(требует уточнения, чем это реализовать на фабрике)")
        if kind == "gap":
            d.statement_because = (f"«{d.a}»→«{d.b}» и «{d.b}»→«{d.c}», но прямой связи "
                                   f"«{d.a}»→«{d.c}» в корпусе нет (разрыв Свонсона)")
        else:
            q = chain[0].get("quote", "")
            d.statement_because = f"источник прямо связывает «{d.a}» и «{d.c}»: «{q[:120]}»"
        res.append(d)
    res.sort(key=lambda x: -x.score)
    return res


def _dedup(discoveries):
    seen, out = set(), []
    for d in discoveries:
        key = (d.a.lower(), d.c.lower())
        if key in seen:
            continue
        seen.add(key); out.append(d)
    return out


def discover(kg, kpi="", limit=10):
    kt = _tokens(kpi)
    gaps = score(kg, find_gaps(kg), kt, kind="gap")
    direct = score(kg, find_direct(kg, kt), kt, kind="direct")
    merged = _dedup(gaps + direct)   # разрывы приоритетнее прямых (у них выше relevance)
    if len(merged) < limit and kg.g.number_of_edges():
        # добираем ведущими связями по новизне (KPI-независимо), релевантные — выше
        merged = _dedup(merged + score(kg, _all_as_direct(kg), kt, kind="direct"))
    merged.sort(key=lambda x: (-x.relevance, -x.score))
    return merged[:limit]
