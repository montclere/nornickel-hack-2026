from __future__ import annotations

import re
from dataclasses import dataclass, field

from factory.tracka.reader import ELEMENT_SYMBOLS, PRIMARY_ELEMENT

_ELEMENT_SYNONYMS = {
    "Ni": [r"никел", r"nickel", r"\bni\b"],
    "Cu": [r"медь", r"медн", r"меди\b", r"copper", r"\bcu\b"],
    "Co": [r"кобальт", r"cobalt", r"\bco\b"],
    "Pt": [r"платин", r"platinum", r"\bpt\b"],
    "Pd": [r"паллад", r"palladium", r"\bpd\b"],
    "Au": [r"золот", r"gold", r"\bau\b"],
    "Ag": [r"серебр", r"silver", r"\bag\b"],
    "Fe": [r"желез", r"\biron\b", r"\bfe\b"],
    "Zn": [r"цинк", r"zinc", r"\bzn\b"],
    "Pb": [r"свинец", r"свинц", r"\blead\b", r"\bpb\b"],
    "S": [r"\bсер[аыу]\b", r"\bsulfur\b", r"\bsulphur\b"],
}

_REDUCE_WORDS = [r"снизит", r"сократит", r"уменьшит", r"снижени", r"потер", r"reduce", r"loss", r"lower"]
_INCREASE_WORDS = [r"повысит", r"увеличит", r"поднят", r"извлечени", r"improve", r"increase", r"recover"]

_CONSTRAINTS = [
    ("без нового оборудования",
     ["без нового оборудован", "без установки нового оборудован", "без закупки оборудован",
      "существующим оборудован", "без капитальных затрат", "без капзатрат", "без capex",
      "минимум капзатрат", "no new equipment"], "equipment"),
    ("без новых реагентов",
     ["без новых реагент", "без закупки реагент", "существующими реагент",
      "не менять реагент", "без смены реагент", "без новой химии"], "reagent"),
    ("сохранить качество концентрата",
     ["сохранить качество концентрат", "без потери качеств", "не снижая качеств",
      "не ухудшая качеств", "без снижения качеств", "не в ущерб качеству"], "quality"),
    ("без снижения производительности",
     ["без снижения производительн", "не снижая производительн", "сохранить производительн",
      "без потери производительн"], "throughput"),

    ("ограниченный бюджет",
     ["мало бюджет", "ограниченн бюджет", "ограничен бюджет", "небольшой бюджет", "низкий бюджет",
      "мало денег", "минимум затрат", "минимальные затрат", "малозатратн", "недорог",
      "бюджетно", "low budget", "limited budget"], "budget"),
]

REAGENT_FAMILY = "реагентный режим / кинетика флотации"

_NAMED_REAGENT_PATTERNS = [
    r"без\s+(?:применения\s+|использования\s+)?реагента\s+([a-zа-яё][a-zа-яё0-9\- ]{1,30}?)(?=[,.;)]|$| без| и |\s{2})",
    r"не\s+использовать\s+реагент[а-я]*\s+([a-zа-яё][a-zа-яё0-9\- ]{1,30}?)(?=[,.;)]|$| без| и )",
]

def _detect_named_reagents(low: str) -> list:
    names = []
    for pat in _NAMED_REAGENT_PATTERNS:
        for m in re.finditer(pat, low):
            name = m.group(1).strip()
            if name and name not in names:
                names.append(name)
    return names

@dataclass
class Intent:
    kpi_text: str
    target_element: str
    element_detected: bool = True
    element_in_schema: bool = True
    requested_element: str | None = None
    direction: str = "improve"
    no_new_equipment: bool = False
    matched_constraints: list = field(default_factory=list)
    constraints: list = field(default_factory=list)
    mentioned_elements: list = field(default_factory=list)

def warn_intent(intent: "Intent", kpi: str, emit=print, schema_symbols=ELEMENT_SYMBOLS) -> bool:
    if not intent.element_detected:
        emit(f"металл в KPI не указан — гипотезы построены по ВСЕМ элементам отчёта "
             f"({', '.join(schema_symbols)}). Чтобы сузить до одного — упомяните его "
             f"явно (напр. «медь»/«Cu»).")
        return False
    if not intent.element_in_schema:
        emit(f"KPI просит «{intent.requested_element}», но в отчёте по хвостам этого "
             f"элемента НЕТ (схема: {', '.join(schema_symbols)}). Детерминированную "
             f"диагностику хвостов по «{intent.requested_element}» построить не из чего "
             f"— она НЕ подменяется никелем. Используйте отчёт с этим элементом или "
             f"ищите гипотезы в литературе (ветка Б).")
        return True
    return False

def _detect_elements(low: str) -> list:
    hits = []
    for sym, pats in _ELEMENT_SYNONYMS.items():
        pos = min((m.start() for p in pats for m in [re.search(p, low)] if m), default=None)
        if pos is not None:
            hits.append((pos, sym))
    return [sym for _, sym in sorted(hits)]

def parse_intent(kpi: str, schema_symbols=ELEMENT_SYMBOLS) -> Intent:
    if not kpi or not kpi.strip():
        raise ValueError("KPI не задан. Без него неясно, что оптимизировать — "
                         "передайте --kpi \"...\" (например: --kpi "
                         "\"снизить потери никеля с хвостами флотации\").")
    low = kpi.lower()
    schema_symbols = tuple(schema_symbols)

    mentioned = _detect_elements(low)
    in_schema = [s for s in mentioned if s in schema_symbols]

    if in_schema:
        element, detected, elem_in_schema, requested = in_schema[0], True, True, in_schema[0]
    elif mentioned:
        element, detected, elem_in_schema, requested = PRIMARY_ELEMENT, True, False, mentioned[0]
    else:
        element, detected, elem_in_schema, requested = PRIMARY_ELEMENT, False, True, None

    direction = "reduce" if (any(re.search(w, low) for w in _REDUCE_WORDS)
                             and not any(re.search(w, low) for w in _INCREASE_WORDS)) else "improve"
    cons = [{"tag": tag, "kind": kind} for tag, pats, kind in _CONSTRAINTS
            if any(p in low for p in pats)]

    for name in _detect_named_reagents(low):
        cons.append({"tag": f"без реагента {name}", "kind": "reagent", "name": name})

    return Intent(kpi_text=kpi, target_element=element, element_detected=detected,
                  element_in_schema=elem_in_schema, requested_element=requested,
                  direction=direction,
                  no_new_equipment=any(c["kind"] == "equipment" for c in cons),
                  matched_constraints=[c["tag"] for c in cons], constraints=cons,
                  mentioned_elements=mentioned)

def constraint_violations(intent: "Intent", family: str, needs_equipment: bool,
                          text: str = "") -> list:
    v = []
    low = (text or "").casefold()
    for c in getattr(intent, "constraints", None) or []:
        if c["kind"] == "equipment" and needs_equipment:
            v.append(c["tag"])
        elif c["kind"] == "reagent":
            name = c.get("name")
            if name:
                if name in low:
                    v.append(c["tag"])
            elif family == REAGENT_FAMILY:
                v.append(c["tag"])
    return v
