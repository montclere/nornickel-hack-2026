# -*- coding: utf-8 -*-
"""LLM — ТОЛЬКО оформление текста. Вся логика/метрики уже посчитаны детерминированно.

Phraser переписывает ЕСЛИ/ТО/ПОТОМУ ЧТО более гладко, но проходит анти-галлюцинацию:
если в тексте появились числа/сущности, которых нет в исходной гипотезе, правка
отклоняется и остаётся детерминированный шаблон. По умолчанию пайплайн НЕ зовёт LLM.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from factory.config import LLM_MAX_RETRIES, YANDEX_BASE_URL, YANDEX_MODEL, load_env

# коды, которые имеет смысл повторить (троттлинг/временные сбои сервера)
_RETRY_CODES = {429, 500, 502, 503, 504}


def _retry_after(err):
    try:
        return float(err.headers.get("Retry-After"))
    except (TypeError, ValueError, AttributeError):
        return None


def post_json(url, payload, headers, timeout=90, max_retries=LLM_MAX_RETRIES):
    """POST JSON с экспоненциальным backoff на 429/5xx/сетевые сбои (учитывает Retry-After).

    Общий транспорт для всех сервисов Yandex (LLM, эмбеддинги, OCR)."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"}, method="POST")
    last = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in _RETRY_CODES or attempt == max_retries:
                raise
            ra = _retry_after(e)
            delay = ra if ra is not None else min(2 ** attempt, 30)
            last = e
        except urllib.error.URLError as e:          # SSL/обрыв соединения — тоже повторяем
            if attempt == max_retries:
                raise
            delay = min(2 ** attempt, 30)
            last = e
        time.sleep(delay)
    raise last                                      # недостижимо, но явно


class Yandex:
    """Клиент Yandex AI Studio: chat + эмбеддинги. Для извлечения сущностей и новизны."""

    def __init__(self, model=YANDEX_MODEL, temperature=0.0, max_tokens=2000):
        load_env()
        self.key = os.environ.get("YANDEX_API_KEY")
        self.folder = os.environ.get("YANDEX_FOLDER_ID")
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens

    @property
    def ready(self):
        return bool(self.key and self.folder)

    def _post(self, path, payload, timeout=90):
        return post_json(f"{YANDEX_BASE_URL}/{path}", payload,
                         {"Authorization": f"Api-Key {self.key}"}, timeout)

    def complete(self, system, user, timeout=90):
        payload = {"modelUri": f"gpt://{self.folder}/{self.model}",
                   "completionOptions": {"stream": False, "temperature": self.temperature,
                                         "maxTokens": str(self.max_tokens)},
                   "messages": [{"role": "system", "text": system},
                                {"role": "user", "text": user}]}
        d = self._post("completion", payload, timeout=timeout)
        return d["result"]["alternatives"][0]["message"]["text"]

    def embed(self, text, kind="doc", timeout=30):
        model = "text-search-doc" if kind == "doc" else "text-search-query"
        d = self._post("textEmbedding",
                       {"modelUri": f"emb://{self.folder}/{model}/latest", "text": text[:2000]},
                       timeout=timeout)
        return d["embedding"]


def extract_json(text):
    """Достать JSON (объект/массив) из ответа LLM; берём самую раннюю скобку."""
    t = text.strip()
    if "```" in t:
        parts = t.split("```")
        t = (parts[1] if len(parts) > 1 else t).lstrip()
        if t.startswith("json"):
            t = t[4:]
    opens = [(t.find(o), o, c) for o, c in (("{", "}"), ("[", "]")) if t.find(o) != -1]
    if not opens:
        return None
    opens.sort()
    _, oc, cc = opens[0]
    i = t.find(oc); depth = 0
    for j in range(i, len(t)):
        if t[j] == oc:
            depth += 1
        elif t[j] == cc:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[i:j + 1])
                except json.JSONDecodeError:
                    return None
    return None


class Phraser:
    """Опциональная LLM-полировка формулировок (Yandex). Без ключа — no-op."""

    SYSTEM = ("Ты редактор. Перефразируй инженерную гипотезу гладко и кратко, НИЧЕГО "
              "не добавляя: не вводи новых чисел, классов, реагентов, оборудования. "
              "Верни ТОЛЬКО JSON {\"if\":..,\"then\":..,\"because\":..}.")

    def __init__(self, llm=None):
        self.llm = llm or Yandex(max_tokens=600)

    @property
    def ready(self):
        return self.llm.ready

    def polish(self, hyps):
        if not self.ready:
            return hyps
        for h in hyps:
            try:
                out = self._call(h)
            except Exception:  # noqa: BLE001
                continue
            if out and self._safe(out, h):
                h.statement_if = out.get("if", h.statement_if)
                h.statement_then = out.get("then", h.statement_then)
                h.statement_because = out.get("because", h.statement_because)
        return hyps

    def _call(self, h):
        user = (f"ЕСЛИ: {h.statement_if}\nТО: {h.statement_then}\n"
                f"ПОТОМУ ЧТО: {h.statement_because}")
        out = extract_json(self.llm.complete(self.SYSTEM, user, timeout=60))
        return out if isinstance(out, dict) else None

    @staticmethod
    def _safe(out, h):
        """Анти-галлюцинация: в правке не должно быть новых чисел."""
        orig_nums = set(re.findall(r"\d+", f"{h.statement_if}{h.statement_then}{h.statement_because}"))
        new_nums = set(re.findall(r"\d+", " ".join(str(out.get(k, "")) for k in ("if", "then", "because"))))
        return new_nums.issubset(orig_nums)
