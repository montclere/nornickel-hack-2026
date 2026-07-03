# -*- coding: utf-8 -*-
"""Клиент Yandex AI Studio: чат-комплишн + эмбеддинги. Только stdlib (urllib).

Секреты — из общего baselines/.env (gitignored). В код ничего не зашивается.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.request

BASE = "https://llm.api.cloud.yandex.net/foundationModels/v1"


def load_env():
    here = os.path.dirname(os.path.abspath(__file__))
    d = here
    cands = [os.path.join(here, ".env")]
    for _ in range(4):
        d = os.path.dirname(d)
        cands.append(os.path.join(d, ".env"))
    for p in cands:
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return True
    return False


class Yandex:
    def __init__(self, model="yandexgpt/latest", temperature=0.3, max_tokens=2000):
        load_env()
        self.key = os.environ.get("YANDEX_API_KEY")
        self.folder = os.environ.get("YANDEX_FOLDER_ID")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        # технические метрики (накапливаются по всем вызовам инстанса)
        self.stats = {"completion_calls": 0, "embed_calls": 0,
                      "input_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                      "embed_tokens": 0, "api_seconds": 0.0}

    @property
    def ready(self):
        return bool(self.key and self.folder)

    def _post(self, path, payload, timeout=60, retries=3):
        req = urllib.request.Request(
            f"{BASE}/{path}", data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Api-Key {self.key}",
                     "Content-Type": "application/json"}, method="POST")
        last = None
        for attempt in range(retries):
            try:
                t0 = time.perf_counter()
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    d = json.loads(r.read().decode("utf-8"))
                self.stats["api_seconds"] += time.perf_counter() - t0
                return d
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise last

    def complete(self, system, user, timeout=90):
        if not self.ready:
            raise RuntimeError("нет YANDEX_API_KEY / YANDEX_FOLDER_ID (.env)")
        payload = {
            "modelUri": f"gpt://{self.folder}/{self.model}",
            "completionOptions": {"stream": False, "temperature": self.temperature,
                                  "maxTokens": str(self.max_tokens)},
            "messages": [{"role": "system", "text": system},
                         {"role": "user", "text": user}],
        }
        d = self._post("completion", payload, timeout=timeout)
        u = d["result"].get("usage", {})
        self.stats["completion_calls"] += 1
        self.stats["input_tokens"] += int(u.get("inputTextTokens", 0) or 0)
        self.stats["completion_tokens"] += int(u.get("completionTokens", 0) or 0)
        self.stats["total_tokens"] += int(u.get("totalTokens", 0) or 0)
        return d["result"]["alternatives"][0]["message"]["text"]

    def embed(self, text, kind="doc", timeout=30):
        """Векторное представление текста (kind: 'doc' | 'query')."""
        model = "text-search-doc" if kind == "doc" else "text-search-query"
        payload = {"modelUri": f"emb://{self.folder}/{model}/latest", "text": text[:2000]}
        d = self._post("textEmbedding", payload, timeout=timeout)
        self.stats["embed_calls"] += 1
        self.stats["embed_tokens"] += int(d.get("numTokens", 0) or 0)
        return d["embedding"]


def cosine(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def extract_json(text):
    """Достать JSON-массив/объект из ответа LLM, терпя ```-ограждения и мусор."""
    t = text.strip()
    if "```" in t:
        parts = t.split("```")
        t = parts[1] if len(parts) > 1 else t
        if t.startswith("json"):
            t = t[4:]
    for oc, cc in (("[", "]"), ("{", "}")):
        i = t.find(oc)
        if i == -1:
            continue
        depth = 0
        for j in range(i, len(t)):
            if t[j] == oc:
                depth += 1
            elif t[j] == cc:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[i:j + 1])
                    except json.JSONDecodeError:
                        break
    return None
