# -*- coding: utf-8 -*-
"""Разбор запроса пользователя (KPI + ограничения в свободном тексте). ДЕТЕРМИНИРОВАННО
(ключевые слова/regex) — намеренно НЕ через LLM: это влияет на диагноз в детерминированном
ядре (generator.py/metrics.py), а его инвариант — воспроизводимость без сети/ключей.

Точка роста: `parse_intent()` — единственное место, которое трактует свободный текст
KPI/промпта. Сюда позже подключается LLM-версия (по образцу llm.Phraser — опциональный
слой поверх, который может расширить/переопределить Intent), не трогая ядро — оно ест
уже разобранный `Intent`, откуда бы он ни взялся.

Раньше был критичный баг: генератор гипотез всегда оптимизировал под первый элемент
(Ni), игнорируя KPI целиком — даже «снизить потери меди» давал Ni-гипотезы. Здесь это
чинится: целевой элемент явно извлекается из текста запроса.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from factory.reader import ELEMENT_SYMBOLS, PRIMARY_ELEMENT

# синонимы элемента в свободном русском/английском тексте → символ (ELEMENT_SYMBOLS)
_ELEMENT_SYNONYMS = {
    "Ni": [r"никел", r"nickel", r"\bni\b"],
    "Cu": [r"мед[ьиь]", r"медн", r"copper", r"\bcu\b"],
}

# фраза-ограничение в тексте → что она значит для фильтрации (сейчас — одна, самая
# частая по формулировке кейса; список расширяется по мере появления новых кейсов)
_NO_EQUIPMENT_PHRASES = [
    "без нового оборудования", "без установки нового оборудования",
    "без закупки оборудования", "существующим оборудованием",
    "без капитальных затрат", "без capex", "no new equipment",
]


@dataclass
class Intent:
    kpi_text: str
    target_element: str                          # "Ni"/"Cu" — на что оптимизировать диагноз
    element_detected: bool = True                 # False — элемент не найден в тексте, взят дефолт
    no_new_equipment: bool = False                # запрет на вмешательства с новым оборудованием
    matched_constraints: list = field(default_factory=list)  # что распознано (для прозрачности)


def parse_intent(kpi: str) -> Intent:
    """Разобрать KPI/промпт по ключевым словам. KPI ОБЯЗАН быть непустым — это
    ответственность вызывающего кода (CLI требует --kpi). Если элемент в тексте не
    упомянут явно — берём PRIMARY_ELEMENT, но помечаем element_detected=False, чтобы
    вызывающий код мог явно предупредить пользователя, а не молчать об этом."""
    if not kpi or not kpi.strip():
        raise ValueError("KPI не задан. Без него неясно, что оптимизировать — "
                         "передайте --kpi \"...\" (например: --kpi "
                         "\"снизить потери никеля с хвостами флотации\").")
    low = kpi.lower()

    element, detected = PRIMARY_ELEMENT, False
    for sym in ELEMENT_SYMBOLS:
        if any(re.search(pat, low) for pat in _ELEMENT_SYNONYMS.get(sym, [])):
            element, detected = sym, True
            break

    hits = [p for p in _NO_EQUIPMENT_PHRASES if p in low]

    return Intent(kpi_text=kpi, target_element=element, element_detected=detected,
                 no_new_equipment=bool(hits), matched_constraints=hits)
