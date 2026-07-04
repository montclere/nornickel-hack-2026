# -*- coding: utf-8 -*-
"""Мировые практики: веб-поиск подтверждения вмешательства — ДЕТЕРМИНИРОВАННО, БЕЗ LLM.

Работает без ключа Yandex (в отличие от прошлой LLM-версии): запрос строится доменным
словарём RU→EN (см. openalex._en_query) + русский запрос, страницы грузятся, и из текста
берётся РЕАЛЬНОЕ предложение, содержащее термины вмешательства, — это и цитата, и
«практика». Заземление честное: цитата дословно есть на странице (цитатный гейт по
построению), несёт URL и домен. Нет сети/цитаты → None (не выдумываем).

Даёт «ближайших соседей»: русскоязычные отраслевые/новостные домены (конкуренты,
журналы) поднимаются в выдаче наравне с мировыми вендорами/журналами.

Приватность: наружу уходят только обезличенные термины вмешательства, не данные фабрик.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
import urllib.parse
from dataclasses import asdict, dataclass

from factory.client import get_text
from factory.config import (WEB_CACHE, WEB_FETCH_TIMEOUT, WEB_INDUSTRIAL_DOMAINS,
                            WEB_MAX_HYPS, WEB_MAX_RESULTS, WEB_MIN_QUOTE_CHARS,
                            WEB_MIN_QUOTE_WORDS, WEB_PAGE_CHARS, WEB_RU_DOMAINS,
                            WEB_SEARCH_ENABLED)
from factory.openalex import _en_query               # общий доменный словарь RU→EN

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


@dataclass
class WorldPractice:
    practice: str        # предложение-практика (оно же заземление)
    quote: str           # дословная фраза из источника (== practice)
    url: str
    site: str
    query: str


# ---------- утилиты ----------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _canon(s: str) -> str:
    """Только буквы/цифры, без регистра и пунктуации — для сравнения цитаты с заголовком
    устойчиво к кавычкам/пробелам/пунктуации (используется в гейте качества)."""
    return re.sub(r"[^0-9a-zа-яё]+", "", (s or "").lower())


def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    except Exception:  # noqa: BLE001
        return ""


def _is_industrial(url: str) -> bool:
    d = _domain(url)
    return any(dom in d for dom in WEB_INDUSTRIAL_DOMAINS)


def _is_ru(url: str) -> bool:
    d = _domain(url)
    return d.endswith(".ru") or any(dom in d for dom in WEB_RU_DOMAINS)


def _rank_key(url: str):
    # русские отраслевые — вперёд (ближайшие соседи), затем прочие индустриальные, затем остальное
    return (0 if _is_ru(url) else 1 if _is_industrial(url) else 2)


def _get(url: str, timeout=WEB_FETCH_TIMEOUT) -> str:
    return get_text(url, headers={"User-Agent": _UA, "Accept-Language": "ru,en;q=0.8"},
                    timeout=timeout, source="web", max_retries=1)


def _strip_html(doc: str, limit=WEB_PAGE_CHARS) -> str:
    doc = re.sub(r"(?is)<(script|style|noscript|head)[^>]*>.*?</\1>", " ", doc)
    doc = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", doc)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", doc))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()[:limit]


def _sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [s.strip() for s in parts if 40 <= len(s.strip()) <= 400]


def _pick_sentence(text: str, terms: set) -> tuple:
    """Предложение с максимумом терминов вмешательства → (предложение, число попаданий)."""
    best, hits = "", 0
    for s in _sentences(text):
        low = s.lower()
        h = sum(1 for t in terms if t in low)
        if h > hits:
            best, hits = s, h
    return best, hits


# ---------- контент страницы: тело без обвязки (фикс «цитаты-заголовки») ----------
# Раньше в LLM уходили первые N символов страницы «как есть» — то есть title, меню,
# навигация и cookie-баннеры. Модель честно выбирала «цитату» из этого мусора —
# получался заголовок страницы: он дословно есть на странице (гейт проходил), но
# ничего не подтверждает. Теперь: (1) обвязка вырезается, (2) текст режется на
# СОДЕРЖАТЕЛЬНЫЕ абзацы, (3) в LLM идут абзацы, релевантные вмешательству,
# (4) после LLM цитата проходит детерминированный гейт КАЧЕСТВА (не заголовок).

_DROP_TAGS = ("script", "style", "noscript", "head", "header", "footer", "nav",
              "aside", "form", "svg", "button", "select")


def _page_content(doc: str) -> tuple:
    """HTML → (title, [содержательные абзацы тела]). Заголовки/пункты меню короче
    порога отсеиваются — из них нельзя брать цитату-доказательство."""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", doc)
    title = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip() if m else ""
    for t in _DROP_TAGS:
        doc = re.sub(rf"(?is)<{t}[^>]*>.*?</{t}>", " ", doc)
    # граница абзаца — только КОНЕЦ БЛОЧНОГО ТЕГА (маркер \x00), а не переносы строк
    # в исходнике: иначе <p> с переносами внутри развалится на фрагменты-«абзацы»
    doc = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</tr>|</section>|</article>",
                 "\x00", doc)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", doc))
    paras = []
    for block in text.split("\x00"):
        p = re.sub(r"\s+", " ", block).strip()   # схлопнуть и пробелы, и переносы
        # абзац «содержательный»: достаточно длинный и в основном из букв
        if len(p) >= 60 and sum(ch.isalpha() for ch in p) / len(p) >= 0.5:
            paras.append(p)
    return title, paras


def _tok(s: str) -> set:
    return set(re.findall(r"[а-яёa-z0-9]{3,}", (s or "").lower()))


def _relevant_excerpt(paras: list, qtokens: set, limit=WEB_PAGE_CHARS) -> str:
    """Собрать для LLM выжимку из абзацев, РЕЛЕВАНТНЫХ запросу (пересечение токенов),
    в исходном порядке — а не первые N символов страницы, где живёт обвязка."""
    scored = sorted(((len(_tok(p) & qtokens), i) for i, p in enumerate(paras)),
                    key=lambda t: (-t[0], t[1]))
    picked, total = [], 0
    for _, i in scored:
        if total >= limit:
            break
        picked.append(i); total += len(paras[i]) + 1
    return "\n".join(paras[i] for i in sorted(picked))[:limit]


def _quote_quality(quote: str, title: str, paras: list) -> bool:
    """Цитата — предложение из ОСНОВНОГО текста, а не заголовок/название страницы.
    Детерминированные признаки, поверх дословного гейта:
      • минимум длины и слов (заголовки короткие);
      • не совпадает с <title> страницы (в обе стороны, по канон-форме);
      • абзац-носитель заметно длиннее самой цитаты (иначе это строка-заголовок)."""
    if len(quote) < WEB_MIN_QUOTE_CHARS:
        return False
    if len(re.findall(r"[а-яёa-z0-9]+", quote.lower())) < WEB_MIN_QUOTE_WORDS:
        return False
    cq, ct = _canon(quote), _canon(title)
    if ct and (cq in ct or ct in cq):
        return False
    host = next((p for p in paras if cq in _canon(p)), None)
    if host is not None and len(host) < max(len(quote) + 40, 160):
        return False
    return True


# ---------- поиск (DuckDuckGo HTML, без ключа) ----------

def _search_ddg(query: str, n: int, timeout=WEB_FETCH_TIMEOUT) -> list:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        doc = _get(url, timeout)
    except Exception:  # noqa: BLE001
        return []
    out, seen = [], set()
    for m in re.finditer(r'result__a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', doc, re.S):
        href = m.group(1)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        real = qs.get("uddg", [href])[0]
        if real.startswith("//"):
            real = "https:" + real
        if not real.startswith("http") or real in seen:
            continue
        seen.add(real)
        out.append(real)
        if len(out) >= n * 3:
            break
    out.sort(key=_rank_key)                            # русские/индустриальные — вперёд
    return out[:n]


# ---------- основной класс ----------

class WebPractices:
    """Детерминированно обогащает гипотезы world_practice. Кэш по отпечатку. БЕЗ LLM."""

    def __init__(self, cache_path=WEB_CACHE, log=lambda *a: None, search_fn=None, **_ignore):
        self.cache_path = cache_path
        self.log = log
        # бэкенд поиска инъектируется (DDG по умолчанию; можно подставить Yandex Search
        # API) — сигнатура search_fn(query, n) -> list[url]
        self._search = search_fn or _search_ddg
        self._cache = self._load()

    @property
    def ready(self) -> bool:
        return WEB_SEARCH_ENABLED                       # ключ Yandex больше не нужен

    def _load(self) -> dict:
        if self.cache_path and os.path.exists(self.cache_path):
            try:
                import json
                return json.load(open(self.cache_path, encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def _save(self):
        if not self.cache_path:
            return
        import json
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        json.dump(self._cache, open(self.cache_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    @staticmethod
    def _key(*parts) -> str:
        return hashlib.sha1("|".join(_norm(p) for p in parts).encode("utf-8")).hexdigest()[:16]

    def enrich(self, hyps, extra: str = "", limit=WEB_MAX_HYPS) -> int:
        if not self.ready:
            self.log("веб-поиск выключен (FACTORY_WEB=0) — world_practice остаётся пустым")
            return 0
        found = 0
        for h in hyps[:limit]:
            wp = self.find(h.intervention, h.family, h.target_element, extra)
            if wp:
                h.world_practice = asdict(wp); found += 1
                self.log(f"практика «{h.intervention[:38]}»: {wp.site}")
            else:
                self.log(f"практика «{h.intervention[:38]}»: источник не найден")
        self._save()
        return found

    def find(self, intervention, family="", element="", extra="") -> "WorldPractice | None":
        # v3: версия схемы кэша — поднята после ввода гейта качества цитат, чтобы
        # старые «цитаты-заголовки» не пережили фикс
        key = self._key("v3det", intervention, family, element, extra)
        if key in self._cache:
            c = self._cache[key]
            return WorldPractice(**c) if c else None
        res = self._find_uncached(intervention, family, element, extra)
        self._cache[key] = asdict(res) if res else None
        return res

    def _terms(self, intervention, family, element) -> set:
        """Термины для заземления: русские слова вмешательства + англ. эквиваленты."""
        ru = set(re.findall(r"[а-яё]{5,}", f"{intervention} {family}".lower()))
        en = set(re.findall(r"[a-z]{4,}", _en_query(intervention, family, element).lower()))
        return ru | en

    def _queries(self, intervention, family, element, extra) -> list:
        ru = f"{intervention} обогащение флотация хвосты извлечение {element}".strip()
        en = f"{_en_query(intervention, family, element)} industrial plant"
        qs = [ru, en]
        if extra:
            qs.append(f"{extra} обогащение практика")
        return qs

    def _find_uncached(self, intervention, family, element, extra):
        # ДЕТЕРМИНИРОВАННО (без LLM), но с гейтом качества товарища: тело страницы
        # чистится от обвязки (_page_content срезает nav/меню/шапку), предложение
        # выбирается по терминам вмешательства, и оно обязано пройти _quote_quality
        # (не заголовок/название). Русские соседи ранжируются выше мировых.
        terms = self._terms(intervention, family, element)
        best = None                                     # (score, WorldPractice)
        seen = set()
        for q in self._queries(intervention, family, element, extra):
            for url in self._search(q, WEB_MAX_RESULTS):
                if url in seen:
                    continue
                seen.add(url)
                try:
                    title, paras = _page_content(_get(url))
                except Exception:  # noqa: BLE001
                    continue
                sent, hits = _pick_sentence("\n".join(paras), terms)
                # гейт качества: содержательное предложение из тела, не заголовок/меню
                if hits < 2 or not _quote_quality(sent, title, paras):
                    continue
                # приоритет: русские соседи > индустриальные > прочие; при равенстве — попадания
                score = (-_rank_key(url), hits)
                if best is None or score > best[0]:
                    best = (score, WorldPractice(practice=sent, quote=sent, url=url,
                                                 site=_domain(url), query=q))
            if best and best[0][0] == 0:                # нашли русского соседа — достаточно
                break
        return best[1] if best else None
