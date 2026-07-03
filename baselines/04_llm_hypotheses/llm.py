# -*- coding: utf-8 -*-
"""Тонкий клиент Yandex AI Studio (YandexGPT) — только stdlib (urllib), без зависимостей.

Ключи читаются из окружения / .env (см. load_env). В код секреты не пишутся.
"""
from __future__ import annotations

import json
import os
import urllib.request

ENDPOINT = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


def load_env(path=".env"):
    """Парсер .env (KEY=VALUE) в os.environ. Ищет .env в cwd, рядом с модулем и
    вверх по дереву (единый секрет-файл baselines/.env на все LLM-бейзлайны)."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [path, os.path.join(here, ".env")]
    d = here
    for _ in range(4):  # вверх по родителям
        d = os.path.dirname(d)
        candidates.append(os.path.join(d, ".env"))
    for p in candidates:
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return True
    return False


class YandexLLM:
    def __init__(self, model="yandexgpt/latest", temperature=0.3, max_tokens=2000):
        load_env()
        self.api_key = os.environ.get("YANDEX_API_KEY")
        self.folder = os.environ.get("YANDEX_FOLDER_ID")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.folder)

    def complete(self, system: str, user: str, timeout=60) -> str:
        """Один вызов чат-комплишена. Возвращает текст ответа модели."""
        if not self.ready:
            raise RuntimeError("нет YANDEX_API_KEY / YANDEX_FOLDER_ID (проверьте .env)")
        payload = {
            "modelUri": f"gpt://{self.folder}/{self.model}",
            "completionOptions": {
                "stream": False,
                "temperature": self.temperature,
                "maxTokens": str(self.max_tokens),
            },
            "messages": [
                {"role": "system", "text": system},
                {"role": "user", "text": user},
            ],
        }
        req = urllib.request.Request(
            ENDPOINT, data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Api-Key {self.api_key}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["result"]["alternatives"][0]["message"]["text"]


def extract_json(text: str):
    """Достать JSON (массив/объект) из ответа LLM, терпя ```json-ограждения и мусор."""
    t = text.strip()
    if "```" in t:
        t = t.split("```")[1]
        if t.startswith("json"):
            t = t[4:]
    # найти первый сбалансированный [...] или {...}
    for open_c, close_c in (("[", "]"), ("{", "}")):
        i = t.find(open_c)
        if i == -1:
            continue
        depth = 0
        for j in range(i, len(t)):
            if t[j] == open_c:
                depth += 1
            elif t[j] == close_c:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[i:j + 1])
                    except json.JSONDecodeError:
                        break
    return None
