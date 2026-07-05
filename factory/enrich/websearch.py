from __future__ import annotations

import hashlib
import html
import os
import re
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from factory.config import (
    WEB_CACHE,
    WEB_FETCH_TIMEOUT,
    WEB_FETCH_WORKERS,
    WEB_HYP_WORKERS,
    WEB_INDUSTRIAL_DOMAINS,
    WEB_MAX_HYPS,
    WEB_MAX_RESULTS,
    WEB_MIN_QUOTE_CHARS,
    WEB_MIN_QUOTE_WORDS,
    WEB_PAGE_CHARS,
    WEB_PER_DOMAIN,
    WEB_RU_DOMAINS,
    WEB_SEARCH_ENABLED,
)
from factory.enrich.openalex import _ELEMENT_EN, _en_query
from factory.ext.client import get_text

_ELEMENT_RU = {"Ni": ("никел", "пентландит", "pentlandite", "миллерит", "millerite"),
               "Cu": ("медь", "меди", "медн", "халькопирит", "chalcopyrite", "халькозин"),
               "Co": ("кобальт", "cobalt"), "Pt": ("платин", "platin"),
               "Pd": ("паллад", "pallad"), "Au": ("золот", "gold"),
               "Ag": ("серебр", "silver"), "Fe": ("желез", "iron")}

def _el_terms(element: str) -> set:
    out = set(_ELEMENT_RU.get(element, ()))
    en = _ELEMENT_EN.get(element, "")
    if en:
        out.add(en)
    return out

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

@dataclass
class WorldPractice:
    practice: str
    quote: str
    url: str
    site: str
    query: str

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()

def _canon(s: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", "", (s or "").lower())

def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""

def _is_industrial(url: str) -> bool:
    d = _domain(url)
    return any(dom in d for dom in WEB_INDUSTRIAL_DOMAINS)

def _is_ru(url: str) -> bool:
    d = _domain(url)
    return d.endswith(".ru") or any(dom in d for dom in WEB_RU_DOMAINS)

def _rank_key(url: str):

    return (0 if _is_ru(url) else 1 if _is_industrial(url) else 2)

def _get(url: str, timeout=WEB_FETCH_TIMEOUT) -> str:
    return get_text(url, headers={"User-Agent": _UA, "Accept-Language": "ru,en;q=0.8"},
                    timeout=timeout, source="web", max_retries=0,
                    max_bytes=700_000, accept_types=("text/",))

def _strip_html(doc: str, limit=WEB_PAGE_CHARS) -> str:
    doc = re.sub(r"(?is)<(script|style|noscript|head)[^>]*>.*?</\1>", " ", doc)
    doc = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", doc)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", doc))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()[:limit]

def _sentences(text: str) -> list:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [s.strip() for s in parts if 40 <= len(s.strip()) <= 400]

def _pick_sentence(text: str, terms: set, el_terms=frozenset()) -> tuple:
    best, bkey, bhits = "", (-1, -1), 0
    for s in _sentences(text):
        low = s.lower()
        h = sum(1 for t in terms if t in low)
        if h == 0:
            continue

        el = 1 if (h >= 2 and any(t in low for t in el_terms)) else 0
        key = (el, h)
        if key > bkey:
            best, bkey, bhits = s, key, h
    return best, bhits

_DROP_TAGS = ("script", "style", "noscript", "head", "header", "footer", "nav",
              "aside", "form", "svg", "button", "select")

def _page_content(doc: str) -> tuple:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", doc)
    title = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip() if m else ""
    for t in _DROP_TAGS:
        doc = re.sub(rf"(?is)<{t}[^>]*>.*?</{t}>", " ", doc)

    doc = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</tr>|</section>|</article>",
                 "\x00", doc)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", doc))
    paras = []
    for block in text.split("\x00"):
        p = re.sub(r"\s+", " ", block).strip()

        if len(p) >= 60 and sum(ch.isalpha() for ch in p) / len(p) >= 0.5:
            paras.append(p)
    return title, paras

def _tok(s: str) -> set:
    return set(re.findall(r"[а-яёa-z0-9]{3,}", (s or "").lower()))

def _relevant_excerpt(paras: list, qtokens: set, limit=WEB_PAGE_CHARS) -> str:
    scored = sorted(((len(_tok(p) & qtokens), i) for i, p in enumerate(paras)),
                    key=lambda t: (-t[0], t[1]))
    picked, total = [], 0
    for _, i in scored:
        if total >= limit:
            break
        picked.append(i); total += len(paras[i]) + 1
    return "\n".join(paras[i] for i in sorted(picked))[:limit]

def _quote_quality(quote: str, title: str, paras: list) -> bool:
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

def _yandex_search_creds() -> tuple:
    key = os.environ.get("YANDEX_SEARCH_KEY") or os.environ.get("YANDEX_API_KEY")
    return key, os.environ.get("YANDEX_FOLDER_ID")

def yandex_search_ready() -> bool:
    key, folder = _yandex_search_creds()

    return bool(key and folder and key.isascii() and folder.isascii() and len(key) > 20)

def _search_yandex(query: str, n: int, timeout=WEB_FETCH_TIMEOUT) -> list:
    import base64

    from factory.ext.client import post_json
    key, folder = _yandex_search_creds()
    payload = {
        "query": {"searchType": "SEARCH_TYPE_RU", "queryText": query,
                  "familyMode": "FAMILY_MODE_NONE", "fixTypoMode": "FIX_TYPO_MODE_ON"},
        "folderId": folder,
        "responseFormat": "FORMAT_XML",
        "l10n": "LOCALIZATION_RU",
    }
    d = post_json("https://searchapi.api.cloud.yandex.net/v2/web/search", payload,
                  headers={"Authorization": f"Api-Key {key}"},
                  timeout=timeout, source="search", max_retries=2)
    xml = base64.b64decode(d.get("rawData", "")).decode("utf-8", "ignore")
    out, seen = [], set()
    for m in re.finditer(r"<url>(.*?)</url>", xml):
        u = html.unescape(m.group(1).strip())
        if _domain(u).endswith("yandex.ru"):
            continue
        if u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= n * 3:
            break
    out.sort(key=_rank_key)
    return out[:n]

def smart_search(query: str, n: int, timeout=WEB_FETCH_TIMEOUT) -> list:
    if yandex_search_ready():
        try:
            res = _search_yandex(query, n, timeout)
            if res:
                return res
        except Exception:
            pass
    return _search_ddg(query, n, timeout)

def _search_ddg(query: str, n: int, timeout=WEB_FETCH_TIMEOUT) -> list:
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    try:
        doc = _get(url, timeout)
    except Exception:
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
    out.sort(key=_rank_key)
    return out[:n]

_PAGE_CACHE: dict = {}
_PAGE_LOCK = threading.Lock()

def _fetch_page(url: str):
    with _PAGE_LOCK:
        if url in _PAGE_CACHE:
            return _PAGE_CACHE[url]
    try:
        res = _page_content(_get(url))
    except Exception:
        res = None
    with _PAGE_LOCK:
        _PAGE_CACHE[url] = res
    return res

def _prefetch(urls: list) -> None:
    todo = [u for u in urls if u not in _PAGE_CACHE]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=min(WEB_FETCH_WORKERS, len(todo))) as ex:
        list(ex.map(_fetch_page, todo))

class WebPractices:

    def __init__(self, cache_path=WEB_CACHE, log=lambda *a: None, search_fn=None, **_ignore):
        self.cache_path = cache_path
        self.log = log
        self._lock = threading.Lock()

        self._search = search_fn or smart_search
        self._cache = self._load()

    @property
    def ready(self) -> bool:
        return WEB_SEARCH_ENABLED

    def _load(self) -> dict:
        if self.cache_path and os.path.exists(self.cache_path):
            try:
                import json
                return json.load(open(self.cache_path, encoding="utf-8"))
            except Exception:
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

        batch = hyps[:limit]
        found = 0
        workers = max(1, min(WEB_HYP_WORKERS, len(batch)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(
                lambda h: self.find(h.intervention, h.family, h.target_element, extra),
                batch))
        for h, wp in zip(batch, results):
            if wp:
                h.world_practice = asdict(wp); found += 1
                self.log(f"практика «{h.intervention[:38]}»: {wp.site}")
            else:
                self.log(f"практика «{h.intervention[:38]}»: источник не найден")
        self._save()
        return found

    def find(self, intervention, family="", element="", extra="") -> "WorldPractice | None":

        key = self._key("v6sent", intervention, family, element, extra)
        with self._lock:
            hit = self._cache.get(key)
        if hit:
            return WorldPractice(**hit)
        res = self._find_uncached(intervention, family, element, extra)

        if res:
            with self._lock:
                self._cache[key] = asdict(res)
        return res

    def _terms(self, intervention, family, element) -> set:
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

        terms = self._terms(intervention, family, element)
        el_terms = _el_terms(element)

        seen, per_domain, groups = set(), {}, []
        for q in self._queries(intervention, family, element, extra):
            urls = []
            for url in self._search(q, WEB_MAX_RESULTS):
                d = _domain(url)
                if url in seen or per_domain.get(d, 0) >= WEB_PER_DOMAIN:
                    continue
                seen.add(url); per_domain[d] = per_domain.get(d, 0) + 1
                urls.append(url)
            if urls:
                groups.append((q, urls))

        total = 0
        capped = []
        for q, urls in groups:
            take = urls[:max(0, WEB_MAX_RESULTS - total)]
            total += len(take)
            if take:
                capped.append((q, take))
        groups = capped

        _prefetch([u for _, urls in groups for u in urls])

        best = None
        for q, urls in groups:
            for url in urls:
                got = _fetch_page(url)
                if got is None:
                    continue
                title, paras = got
                sent, hits = _pick_sentence("\n".join(paras), terms, el_terms)

                if hits < 2 or not _quote_quality(sent, title, paras):
                    continue

                low = f"{sent} {title}".lower()
                el_hit = int(any(t in low for t in el_terms))
                score = (el_hit, -_rank_key(url), hits)
                if best is None or score > best[0]:
                    best = (score, WorldPractice(practice=sent, quote=sent, url=url,
                                                 site=_domain(url), query=q))

            if best and best[0][0] == 1 and best[0][1] == 0:
                break
        return best[1] if best else None
