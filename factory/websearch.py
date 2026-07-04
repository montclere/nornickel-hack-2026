# -*- coding: utf-8 -*-
"""Мировые практики: веб-поиск внешнего подтверждения вмешательства в ПРОМЫШЛЕННОЙ
практике обогащения — заполняет поле `world_practice` гипотезы.

Тот же принцип, что и во всём проекте: LLM только ПОНИМАЕТ найденный текст, а не
сочиняет факты. Итоговое подтверждение обязано нести (1) реальный URL и (2) ДОСЛОВНУЮ
цитату, которая подстрокой присутствует на загруженной странице (цитатный гейт). Всё
кэшируется по отпечатку запроса → воспроизводимо и заземлено. Нет сети/ключа/цитаты →
возвращаем None (честнее пустоты, чем выдуманная «мировая практика»).

Приоритет промышленным/материаловедческим доменам (WEB_INDUSTRIAL_DOMAINS: MITS NIMS,
профильные журналы, вендоры оборудования). Двуязычно: ищем на RU и EN, EN-материалы
LLM понимает и резюмирует на RU.

Поток: intervention → пара запросов (RU/EN) → поиск (DuckDuckGo, без ключа) →
загрузка топ-страниц → LLM выбирает источник и дословную цитату → гейт → WorldPractice.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass

from factory.config import (WEB_CACHE, WEB_FETCH_TIMEOUT, WEB_INDUSTRIAL_DOMAINS,
                            WEB_MAX_HYPS, WEB_MAX_RESULTS, WEB_MIN_QUOTE_CHARS,
                            WEB_MIN_QUOTE_WORDS, WEB_PAGE_CHARS, WEB_SEARCH_ENABLED)
from factory.llm import Yandex, extract_json

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


@dataclass
class WorldPractice:
    practice: str        # RU-резюме: где и как применяется, результат
    quote: str           # дословная цитата из источника (в языке оригинала)
    url: str             # реальный адрес страницы
    site: str            # домен (для отображения «источник: nims.go.jp»)
    query: str           # по какому запросу нашли (провенанс)


# ---------- утилиты ----------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _canon(s: str) -> str:
    """Только буквы/цифры, без регистра и пунктуации — гасит дрейф кавычек/пробелов
    в цитате LLM, но сохраняет дословную непрерывность (не пускает пересказ)."""
    return re.sub(r"[^0-9a-zа-яё]+", "", (s or "").lower())


def _quote_on_page(quote: str, page: str) -> bool:
    """Цитатный гейт: дословная фраза действительно на странице? Пробуем и по
    нормализованным пробелам, и по алфанумерике (устойчиво к разметке/пунктуации)."""
    if _norm(quote) in _norm(page):
        return True
    cq = _canon(quote)
    return len(cq) >= 20 and cq in _canon(page)


def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    except Exception:  # noqa: BLE001
        return ""


def _is_industrial(url: str) -> bool:
    d = _domain(url)
    return any(dom in d for dom in WEB_INDUSTRIAL_DOMAINS)


def _get(url: str, timeout=WEB_FETCH_TIMEOUT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Accept-Language": "en,ru;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(1_500_000)
        enc = (r.headers.get_content_charset() or "utf-8")
    return raw.decode(enc, "ignore")


def _strip_html(doc: str, limit=WEB_PAGE_CHARS) -> str:
    """Грубо вытащить читаемый текст: срезать script/style/теги, схлопнуть пробелы."""
    doc = re.sub(r"(?is)<(script|style|noscript|head)[^>]*>.*?</\1>", " ", doc)
    doc = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", doc)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", doc))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:limit]


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
    """Вернуть [(url, title)] по запросу. DDG отдаёт ссылки через редирект uddg=..."""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        doc = _get(url, timeout)
    except Exception:  # noqa: BLE001
        return []
    out, seen = [], set()
    for m in re.finditer(r'result__a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', doc, re.S):
        href, title = m.group(1), _strip_html(m.group(2), 200)
        pr = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(pr.query)
        real = qs.get("uddg", [href])[0]
        if real.startswith("//"):
            real = "https:" + real
        if not real.startswith("http") or real in seen:
            continue
        seen.add(real)
        out.append((real, title))
        if len(out) >= n * 3:
            break
    # промышленные домены — вперёд, дальше исходный порядок выдачи
    out.sort(key=lambda t: 0 if _is_industrial(t[0]) else 1)
    return out[:n]


# ---------- основной класс ----------

class WebPractices:
    """Обогащает гипотезы полем world_practice. Кэш по отпечатку → воспроизводимо."""

    SYSTEM = ("Ты инженер-обогатитель. Тебе дают вмешательство и пронумерованные "
              "выдержки с веб-страниц. Определи, ПОДТВЕРЖДАЕТ ли какой-то источник "
              "ПРОМЫШЛЕННОЕ применение этого вмешательства в обогащении руд/переработке "
              "хвостов (внедрение на фабрике, пилот, промышленный опыт — не только "
              "лабораторная теория). Верни ТОЛЬКО JSON: "
              '{"found": true|false, "source": <номер>, '
              '"quote": "<дословная фраза из ЭТОГО источника, язык оригинала>", '
              '"practice": "<1-2 предложения по-русски: где и как применяют, результат>"}. '
              "ТРЕБОВАНИЯ К quote: это ПОЛНОЕ ПРЕДЛОЖЕНИЕ (или два) из основного текста, "
              "минимум 10 слов, скопированное ДОСЛОВНО. Предложение само по себе должно "
              "подтверждать промышленное применение (где / что сделали / результат). "
              "ЗАПРЕЩЕНО брать в quote заголовок страницы, название статьи, пункт меню "
              "или подпись ссылки — такая цитата будет отброшена автоматически. Если ни "
              "один источник не подтверждает промышленное применение — found=false.")

    def __init__(self, llm=None, cache_path=WEB_CACHE, log=lambda *a: None):
        self.llm = llm or Yandex(temperature=0.0, max_tokens=800)
        self.cache_path = cache_path
        self.log = log
        self._cache = self._load()

    @property
    def ready(self) -> bool:
        return WEB_SEARCH_ENABLED and self.llm.ready

    # --- кэш ---
    def _load(self) -> dict:
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
    def _key(*parts) -> str:
        return hashlib.sha1("|".join(_norm(p) for p in parts).encode("utf-8")).hexdigest()[:16]

    # --- API ---
    def enrich(self, hyps, extra: str = "", limit=WEB_MAX_HYPS) -> int:
        """Заполнить world_practice у топ-`limit` гипотез. Возвращает число найденных."""
        if not self.ready:
            self.log("веб-поиск недоступен (выключен или нет ключа Yandex) — "
                     "world_practice остаётся пустым")
            return 0
        found = 0
        for h in hyps[:limit]:
            wp = self.find(h.intervention, h.family, h.target_element, extra)
            if wp:
                h.world_practice = asdict(wp)
                found += 1
                self.log(f"✓ практика для «{h.intervention}»: {wp.site}")
            else:
                self.log(f"· практика для «{h.intervention}» не подтверждена цитатой")
        self._save()
        return found

    def find(self, intervention: str, family: str = "", element: str = "",
             extra: str = "") -> WorldPractice | None:
        # v3: версия схемы кэша — поднята после ввода гейта качества цитат, чтобы
        # закэшированные «цитаты-заголовки» из v2 не пережили фикс
        key = self._key("v3", intervention, family, element, extra)
        if key in self._cache:
            c = self._cache[key]
            return WorldPractice(**c) if c else None

        result = self._find_uncached(intervention, family, element, extra)
        self._cache[key] = asdict(result) if result else None
        return result

    def _find_uncached(self, intervention, family, element, extra):
        queries = self._queries(intervention, family, element, extra)
        # токены запроса (RU+EN) — чтобы отдать LLM релевантные абзацы, а не шапку сайта
        qtokens = _tok(" ".join([intervention, family, element, extra] + queries))
        pages, urls_seen = [], set()
        for q in queries:
            for url, _title in _search_ddg(q, WEB_MAX_RESULTS):
                if url in urls_seen:
                    continue
                urls_seen.add(url)
                try:
                    title, paras = _page_content(_get(url))
                except Exception:  # noqa: BLE001
                    continue
                excerpt = _relevant_excerpt(paras, qtokens)
                if len(excerpt) >= 200:                 # есть содержательное тело
                    pages.append((url, title, paras, excerpt, q))
                if len(pages) >= WEB_MAX_RESULTS:
                    break
            if len(pages) >= WEB_MAX_RESULTS:
                break
        if not pages:
            return None

        src_block = "\n\n".join(
            f"[{i+1}] URL: {u}\n{ex}" for i, (u, _t, _p, ex, _q) in enumerate(pages))
        user = (f"Вмешательство: {intervention}\nСемейство: {family}\n"
                f"Целевой элемент: {element}\n\nИсточники:\n{src_block}")
        try:
            out = extract_json(self.llm.complete(self.SYSTEM, user, timeout=90))
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(out, dict) or not out.get("found"):
            return None

        idx = out.get("source")
        if not isinstance(idx, int) or not (1 <= idx <= len(pages)):
            return None
        url, title, paras, _ex, q = pages[idx - 1]
        quote = (out.get("quote") or "").strip()
        body = "\n".join(paras)
        # ГЕЙТ 1 (дословность): фраза обязана быть в теле страницы — иначе галлюцинация.
        # ГЕЙТ 2 (качество): фраза — предложение из текста, а не заголовок/название.
        if not _quote_on_page(quote, body) or not _quote_quality(quote, title, paras):
            return None
        return WorldPractice(practice=(out.get("practice") or "").strip(), quote=quote,
                             url=url, site=_domain(url), query=q)

    def _queries(self, intervention, family, element, extra) -> list:
        """Пара запросов RU/EN. EN-запрос — чтобы доставать промышленные англоязычные
        источники (журналы, MITS NIMS и т.п.), которые LLM затем понимает."""
        base_ru = f"{intervention} обогащение флотация хвосты промышленное внедрение"
        key = self._key("q", intervention, family, element)
        en = self._cache.get("_q_" + key)
        if en is None:
            en = self._translate(intervention, family)
            self._cache["_q_" + key] = en
        base_en = f"{en} mineral processing flotation tailings recovery industrial"
        qs = [base_ru, base_en]
        if extra:
            qs.append(f"{extra} {en} froth flotation recovery")
        return qs

    def _translate(self, intervention, family) -> str:
        """RU-вмешательство → EN-термины (кэшируется). Без ключа — вернуть как есть."""
        if not self.llm.ready:
            return intervention
        try:
            sys = ("Переведи русский термин обогащения руд в 3-6 английских ключевых "
                   "слов для поиска в научной/промышленной литературе. Верни ТОЛЬКО слова.")
            out = self.llm.complete(sys, f"{intervention}. Семейство: {family}", timeout=45)
            return re.sub(r"\s+", " ", out).strip()[:120] or intervention
        except Exception:  # noqa: BLE001
            return intervention
