"""CardPhrasing через Claude API.

LLM ТОЛЬКО оформляет переданные структурированные поля в формат
«ЕСЛИ [воздействие] — ТО [эффект на KPI] — ПОТОМУ ЧТО [механизм]». ЖЁСТКО: ни одного
нового факта/сущности — модели разрешено упоминать только `allowed_entities`. Финальную
постпроверку «никаких новых сущностей» делает домен (`cards.verify_no_new_entities`):
этот адаптер — лишь генератор текста, гарантия заземления — в ядре.

`anthropic` импортируется лениво, чтобы лёгкая установка ядра не требовала SDK; реальные
вызовы — только при mode="real". По умолчанию весь pipeline идёт на FakeCardPhrasing.
"""

from __future__ import annotations

import json

from app.config import Settings, load_settings
from app.service.entities import PhrasedCard
from app.service.errors import PhrasingViolationError

_SYSTEM_PROMPT = (
    "Ты оформляешь карточку научной гипотезы для R&D-центра «Норильский никель». "
    "Тебе дают структурированные поля (origin, intervention, effect_target, mechanism, "
    "allowed_entities, evidence). Твоя ЕДИНСТВЕННАЯ задача — переформулировать их в три "
    "коротких русских поля в формате «ЕСЛИ — ТО — ПОТОМУ ЧТО»:\n"
    "  if  — воздействие (что сделать),\n"
    "  then — эффект на KPI,\n"
    "  because — механизм из цепочки доказательств.\n"
    "ЖЁСТКИЕ ПРАВИЛА: не добавляй НИ ОДНОГО нового факта, числа, реагента, параметра или "
    "процесса. Упоминай только сущности из allowed_entities. Никаких преамбул и markdown — "
    "верни строго JSON с ключами if, then, because."
)

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "if": {"type": "string"},
        "then": {"type": "string"},
        "because": {"type": "string"},
    },
    "required": ["if", "then", "because"],
    "additionalProperties": False,
}


class ClaudeCardPhrasing:
    """Реализация порта CardPhrasing через Claude (structured JSON)."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        settings = settings or load_settings()
        self.model = model or settings.phrasing_model
        self._api_key = api_key

    def phrase(self, pattern_fields: dict) -> PhrasedCard:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - зависит от окружения
            raise PhrasingViolationError(
                "ClaudeCardPhrasing требует anthropic SDK — установите: pip install -e '.[infra]'"
            ) from exc

        client = (
            anthropic.Anthropic(api_key=self._api_key)
            if self._api_key
            else anthropic.Anthropic()
        )
        response = client.messages.create(
            model=self.model,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(pattern_fields, ensure_ascii=False),
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}},
        )
        text = next(block.text for block in response.content if block.type == "text")
        data = json.loads(text)
        # alias-конструктор: `if` — зарезервированное слово, поле зовётся if_
        return PhrasedCard(
            **{"if": data["if"], "then": data["then"], "because": data["because"]}
        )


__all__ = ["ClaudeCardPhrasing"]
