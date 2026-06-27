"""Минимальный Groq chat-хелпер для агента (httpx, OpenAI-совместимый).

Используется в plan (сформулировать поисковый запрос из пробела) и в chat-ответе.
Тот же провайдер, что у извлечения. Без ключа/при ошибке вызывающий код
откатывается на детерминированную ветку — агент не падает.
"""

from __future__ import annotations

import os

import httpx

from app.config import load_settings


def groq_complete(
    prompt: str,
    *,
    system: str = "",
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    max_tokens: int = 200,
    timeout: float = 30.0,
    client: httpx.Client | None = None,
) -> str:
    """Один chat-вызов → текст ответа (без структурирования)."""
    settings = load_settings()
    api_key = api_key or os.getenv("GROQ_API_KEY")
    model = model or settings.extractor_model
    base_url = (base_url or settings.llm_base_url).rstrip("/")
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    http = client or httpx.Client(timeout=timeout)
    resp = http.post(
        f"{base_url}/chat/completions",
        json={"model": model, "temperature": 0, "max_tokens": max_tokens, "messages": messages},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


__all__ = ["groq_complete"]
