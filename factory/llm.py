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
import urllib.request

BASE = "https://llm.api.cloud.yandex.net/foundationModels/v1"
ENDPOINT = f"{BASE}/completion"


def load_env():
    here = os.path.dirname(os.path.abspath(__file__))
    d = here
    for _ in range(4):
        p = os.path.join(d, ".env")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return True
        d = os.path.dirname(d)
    return False


class Yandex:
    """Клиент Yandex AI Studio: chat + эмбеддинги. Для извлечения сущностей и новизны."""

    def __init__(self, model="yandexgpt/latest", temperature=0.0, max_tokens=2000):
        load_env()
        self.key = os.environ.get("YANDEX_API_KEY")
        self.folder = os.environ.get("YANDEX_FOLDER_ID")
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens

    @property
    def ready(self):
        return bool(self.key and self.folder)

    def _post(self, path, payload, timeout=90):
        req = urllib.request.Request(
            f"{BASE}/{path}", data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Api-Key {self.key}",
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

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

    def __init__(self):
        load_env()
        self.key = os.environ.get("YANDEX_API_KEY")
        self.folder = os.environ.get("YANDEX_FOLDER_ID")

    @property
    def ready(self):
        return bool(self.key and self.folder)

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
        payload = {"modelUri": f"gpt://{self.folder}/yandexgpt/latest",
                   "completionOptions": {"stream": False, "temperature": 0.0,
                                         "maxTokens": "600"},
                   "messages": [{"role": "system", "text": self.SYSTEM},
                                {"role": "user", "text": user}]}
        req = urllib.request.Request(
            ENDPOINT, data=json.dumps(payload).encode(),
            headers={"Authorization": f"Api-Key {self.key}",
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode())
        txt = d["result"]["alternatives"][0]["message"]["text"]
        i, j = txt.find("{"), txt.rfind("}")
        return json.loads(txt[i:j + 1]) if i >= 0 else None

    @staticmethod
    def _safe(out, h):
        """Анти-галлюцинация: в правке не должно быть новых чисел."""
        orig_nums = set(re.findall(r"\d+", f"{h.statement_if}{h.statement_then}{h.statement_because}"))
        new_nums = set(re.findall(r"\d+", " ".join(str(out.get(k, "")) for k in ("if", "then", "because"))))
        return new_nums.issubset(orig_nums)
