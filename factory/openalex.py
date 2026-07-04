# -*- coding: utf-8 -*-
"""Доказательное досье гипотезы через OpenAlex — БЕЗ LLM, детерминированно.

Зачем OpenAlex, а не веб-скрейпинг: это чистый научный JSON-API (без ключа, стабилен),
тогда как произвольные сайты 403-ят у половины запросов. На каждую гипотезу отдаёт РЯД
реальных источников с:
  • «важностью» = cited_by_count (реальная цитируемость, а не мнение модели);
  • «причиной/механизмом» = предложением из abstract, где встречаются термины вмешательства;
Заземление честное: цитата — реальная фраза из abstract работы (цитатный гейт по
построению). LLM здесь НЕ участвует: запрос строится детерминированным доменным
словарём RU→EN, ранжирование — по цитируемости×релевантности.

Приватность: наружу уходят только ОБЕЗЛИЧЕННЫЕ англ. термины вмешательства (напр.
"regrinding pentlandite flotation nickel"), никаких данных фабрик.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
from dataclasses import asdict, dataclass

from factory.client import get_json
from factory.config import (OPENALEX_BASE, OPENALEX_CACHE, OPENALEX_ENABLED, OPENALEX_FETCH,
                            OPENALEX_MAILTO, OPENALEX_MAX_HYPS, OPENALEX_PER_HYP)

# Детерминированный доменный словарь RU→EN (термины обогащения). Никакого LLM-перевода:
# домен узкий и фиксированный, поэтому статического словаря достаточно и он воспроизводим.
_TERMS_RU_EN = [
    ("доизмельч", "regrinding"), ("измельч", "grinding"), ("раскрыт", "liberation"),
    ("футеровк", "mill liner"), ("мельниц", "mill"), ("гранулометр", "particle size"),
    ("грохоч", "screening"), ("грохот", "screening"), ("сит", "sieve"),
    ("классифик", "classification"), ("гидроцикл", "hydrocyclone"), ("циклон", "cyclone"),
    ("насадк", "spigot"), ("флотац", "flotation"), ("перечист", "cleaner flotation"),
    ("контрольн", "scavenger flotation"), ("фронт", "flotation circuit"),
    ("контактн", "conditioning"), ("агитац", "agitation"), ("реагент", "reagent"),
    ("собират", "collector"), ("ксантоген", "xanthate"), ("депрессор", "depressant"),
    ("подавл", "depression"), ("купорос", "copper sulphate"), ("извест", "lime"),
    ("пирротин", "pyrrhotite"), ("пентландит", "pentlandite"), ("миллерит", "millerite"),
    ("халькопирит", "chalcopyrite"), ("сросток", "composite particle"), ("шлам", "slimes"),
    ("магнитн", "magnetic separation"), ("кинетик", "flotation kinetics"),
]
_ELEMENT_EN = {"Ni": "nickel", "Cu": "copper", "Co": "cobalt", "Pt": "platinum",
               "Pd": "palladium", "Au": "gold", "Ag": "silver", "Fe": "iron"}


@dataclass
class Evidence:
    title: str
    year: int | None
    cited_by: int
    venue: str
    url: str            # DOI (предпочтительно) или ссылка OpenAlex
    quote: str          # предложение из abstract с термином вмешательства (заземление)
    query: str          # по каким терминам найдено (провенанс)


def _en_query(intervention: str, family: str, element: str) -> str:
    """RU вмешательство+семейство → англ. поисковый запрос (детерминированно, без LLM)."""
    low = f"{intervention} {family}".lower()
    terms = []
    for ru, en in _TERMS_RU_EN:
        if ru in low and en not in terms:
            terms.append(en)
    el = _ELEMENT_EN.get(element, "")
    tail = [t for t in (el, "flotation", "tailings", "recovery") if t]
    return " ".join(terms + tail).strip() or " ".join(tail)


def _reconstruct_abstract(inv: dict | None) -> str:
    """OpenAlex отдаёт abstract как inverted_index {слово: [позиции]} — собираем обратно."""
    if not inv:
        return ""
    positions = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def _sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 25]


def _pick_quote(abstract: str, query: str) -> str:
    """Предложение abstract с максимумом терминов запроса = заземление «причины».
    Это РЕАЛЬНАЯ фраза из abstract (цитатный гейт по построению, без LLM)."""
    qt = {w for w in re.findall(r"[a-z]{4,}", query.lower())}
    best, best_hits = "", 0
    for s in _sentences(abstract):
        hits = sum(1 for w in qt if w in s.lower())
        if hits > best_hits:
            best, best_hits = s, hits
    return best if best_hits else ""


def _domain_relevant(text: str) -> bool:
    """Отсечь нерелевантные работы (OpenAlex может вернуть биомед/химию не по теме)."""
    t = text.lower()
    return any(k in t for k in ("flotation", "froth", "mineral", "ore", "tailings",
                                "beneficiation", "concentrat", "comminution", "grinding"))


class OpenAlexDossier:
    """Собирает досье реальных источников на гипотезу. Кэш по отпечатку → воспроизводимо."""

    def __init__(self, cache_path=OPENALEX_CACHE, log=lambda *a: None):
        self.cache_path = cache_path
        self.log = log
        self._cache = self._load()

    @property
    def ready(self) -> bool:
        return OPENALEX_ENABLED

    def _load(self):
        if self.cache_path and os.path.exists(self.cache_path):
            try:
                return json.load(open(self.cache_path, encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def _save(self):
        if not self.cache_path:
            return
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        json.dump(self._cache, open(self.cache_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    @staticmethod
    def _key(*p):
        return hashlib.sha1("|".join(p).encode("utf-8")).hexdigest()[:16]

    def enrich(self, hyps, limit=OPENALEX_MAX_HYPS) -> int:
        """Прикрепить .dossier (list[Evidence-dict]) к топ-`limit` гипотезам. Запросы к
        OpenAlex идут ПАРАЛЛЕЛЬНО (сеть — узкое место): 6 гипотез за секунды, а не за минуту.
        Возвращает число гипотез, для которых нашлись источники."""
        if not self.ready:
            return 0
        from concurrent.futures import ThreadPoolExecutor
        targets = hyps[:limit]

        def work(h):
            try:
                return h, self.dossier(h.intervention, h.family, h.target_element)
            except Exception:  # noqa: BLE001  (сеть/предохранитель — не роняем весь батч)
                return h, []

        found = 0
        with ThreadPoolExecutor(max_workers=min(6, len(targets) or 1)) as ex:
            for h, ev in ex.map(work, targets):
                h.dossier = [asdict(e) for e in ev]
                if ev:
                    found += 1
                    self.log(f"досье «{h.intervention[:40]}»: {len(ev)} источн. "
                             f"(топ {ev[0].cited_by} цит.)")
        self._save()
        return found

    def dossier(self, intervention, family="", element="") -> list:
        query = _en_query(intervention, family, element)
        key = self._key("v2", query)          # v2: не кэшируем пустое (см. ниже) → старые пустые кэши игнорируются
        if key in self._cache and self._cache[key]:
            return [Evidence(**e) for e in self._cache[key]]
        ev = self._search(query)
        # кэшируем ТОЛЬКО непустой результат: транзиентная ошибка/пустая выдача не должна
        # «отравить» кэш и лишить статей все следующие прогоны с тем же запросом
        if ev:
            self._cache[key] = [asdict(e) for e in ev]
        return ev

    def _search(self, query) -> list:
        params = {"search": query, "per-page": OPENALEX_FETCH, "mailto": OPENALEX_MAILTO,
                  "select": "title,publication_year,cited_by_count,primary_location,"
                            "abstract_inverted_index,doi,id"}
        url = f"{OPENALEX_BASE}/works?" + urllib.parse.urlencode(params)
        try:
            data = get_json(url, headers={"Accept": "application/json"}, timeout=8,
                            source="openalex", max_retries=1)
        except Exception as e:  # noqa: BLE001
            self.log(f"OpenAlex недоступен: {e}")
            return []
        cands = []
        for w in data.get("results", []):
            abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))
            title = w.get("title") or ""
            if not _domain_relevant(f"{title} {abstract}"):
                continue
            quote = _pick_quote(abstract, query) or _pick_quote(title, query)
            if not quote:
                continue
            venue = (((w.get("primary_location") or {}).get("source") or {})
                     .get("display_name")) or ""
            url = w.get("doi") or w.get("id") or ""
            cited = int(w.get("cited_by_count") or 0)
            # релевантность — доля терминов запроса в title+abstract
            qt = {t for t in re.findall(r"[a-z]{4,}", query.lower())}
            hit = sum(1 for t in qt if t in f"{title} {abstract}".lower())
            rel = hit / (len(qt) or 1)
            cands.append((rel, cited, Evidence(
                title=title[:200], year=w.get("publication_year"), cited_by=cited,
                venue=venue[:120], url=url, quote=quote[:300], query=query)))
        # ранг: сперва релевантность, затем важность (цитируемость) — «набор реальных
        # источников: причины + важность по цитируемости» (QA)
        cands.sort(key=lambda c: (round(c[0], 2), c[1]), reverse=True)
        return [e for _, _, e in cands[:OPENALEX_PER_HYP]]
