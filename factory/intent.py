# -*- coding: utf-8 -*-
"""Разбор запроса пользователя (KPI + ограничения в свободном тексте). ДЕТЕРМИНИРОВАННО
(ключевые слова/regex) — намеренно НЕ через LLM: это влияет на диагноз в детерминированном
ядре (generator.py/metrics.py), а его инвариант — воспроизводимость без сети/ключей.

Точка роста: `parse_intent()` — единственное место, которое трактует свободный текст
KPI/промпта. Сюда позже подключается LLM-версия (по образцу llm.Phraser — опциональный
слой поверх, который может расширить/переопределить Intent), не трогая ядро — оно ест
уже разобранный `Intent`, откуда бы он ни взялся.

Раньше был критичный баг: генератор гипотез всегда оптимизировал под первый элемент
(Ni), игнорируя KPI целиком. Он чинится здесь. ВАЖНО (второй виток той же ошибки):
если пользователь просит элемент, которого НЕТ в схеме отчёта (напр. платину, а отчёт —
про Cu-Ni), мы НЕ подменяем его молча на Ni. Такой элемент детектируется отдельно
(`requested_element`) и помечается `element_in_schema=False`, чтобы вызывающий код
(flex.py/pipeline.py) честно сказал: «этого элемента нет в данных этой фабрики», а не
выдал уверенные никелевые гипотезы под видом ответа про платину.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from factory.reader import ELEMENT_SYMBOLS, PRIMARY_ELEMENT

# Синонимы металлов в свободном русском/английском тексте → символ. Список ШИРЕ, чем
# элементы текущей схемы: так мы РАСПОЗНАЁМ упоминание платины/кобальта/золота и т.п.,
# даже если в отчёте их нет, — чтобы явно сообщить об этом, а не молча взять дефолт.
# Границы слова важны: «меди» (потери меди) — да, «медиана» — нет.
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

# направление цели — только для прозрачности вывода (ядро физически решает одну задачу:
# перевести извлекаемую потерю в концентрат). Не влияет на диагноз, но печатается.
_REDUCE_WORDS = [r"снизит", r"сократит", r"уменьшит", r"снижени", r"потер", r"reduce", r"loss", r"lower"]
_INCREASE_WORDS = [r"повысит", r"увеличит", r"поднят", r"извлечени", r"improve", r"increase", r"recover"]

# Реестр ограничений: (tag, [подстроки], kind). kind решает, какие гипотезы конфликтуют:
#   equipment  — требующие НОВОГО оборудования (diag.needs_equipment);
#   reagent    — меняющие реагентный режим (семейство «реагентный режим / кинетика флотации»);
#   quality/throughput — «мягкие» цели: фиксируем и показываем, но НЕ штрафуем (нечем
#                детерминированно доказать вред качеству/производительности конкретной гипотезы).
# Расширяется добавлением строки — без правок ядра. Всё детерминированно (без LLM).
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
]

# семейство, конфликтующее с ограничением «без новых реагентов» (из rules.py)
REAGENT_FAMILY = "реагентный режим / кинетика флотации"

# «без реагента <имя>» — запрет КОНКРЕТНОГО реагента, имя достаём регуляркой:
# «без реагента Finfix 300», «без применения ксантогената», «не использовать КМЦ».
# Имя сохраняется в ограничении и сверяется с ТЕКСТОМ вмешательства гипотезы.
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
    target_element: str                          # символ, под который считает ядро
    element_detected: bool = True                 # False — ни один металл в тексте не найден, взят дефолт
    element_in_schema: bool = True                # False — металл упомянут, но его нет в схеме отчёта
    requested_element: str | None = None          # что реально упомянуто (может быть вне схемы, напр. Pt)
    direction: str = "improve"                    # improve | reduce — только для прозрачности
    no_new_equipment: bool = False                # (совместимость) запрет нового оборудования
    matched_constraints: list = field(default_factory=list)  # теги распознанных ограничений
    constraints: list = field(default_factory=list)          # [{"tag","kind"}] — для генератора
    mentioned_elements: list = field(default_factory=list)   # все распознанные металлы (могут быть вне схемы)


def warn_intent(intent: "Intent", kpi: str, emit=print, schema_symbols=ELEMENT_SYMBOLS) -> bool:
    """Единая точка предупреждений о целевом элементе (используют и pipeline, и flex).
    Возвращает True, если ветку А по хвостам считать НЕ имеет смысла (элемент вне схемы)."""
    if not intent.element_detected:
        emit(f"⚠ элемент не распознан в KPI «{kpi}» — использован дефолт "
             f"({intent.target_element}). Если нужен другой — упомяните его явно "
             f"(напр. «медь»/«Cu»).")
        return False
    if not intent.element_in_schema:
        emit(f"⚠ KPI просит «{intent.requested_element}», но в отчёте по хвостам этого "
             f"элемента НЕТ (схема: {', '.join(schema_symbols)}). Детерминированную "
             f"диагностику хвостов по «{intent.requested_element}» построить не из чего "
             f"— она НЕ подменяется никелем. Используйте отчёт с этим элементом или "
             f"ищите гипотезы в литературе (ветка Б).")
        return True
    return False


def _detect_elements(low: str) -> list:
    """Все металлы, упомянутые в тексте, в порядке первого вхождения."""
    hits = []
    for sym, pats in _ELEMENT_SYNONYMS.items():
        pos = min((m.start() for p in pats for m in [re.search(p, low)] if m), default=None)
        if pos is not None:
            hits.append((pos, sym))
    return [sym for _, sym in sorted(hits)]


def parse_intent(kpi: str, schema_symbols=ELEMENT_SYMBOLS) -> Intent:
    """Разобрать KPI/промпт по ключевым словам. KPI ОБЯЗАН быть непустым — это
    ответственность вызывающего кода (CLI требует --kpi).

    Логика выбора целевого элемента:
      • упомянут металл ИЗ схемы отчёта → берём его (element_in_schema=True);
      • упомянут металл ВНЕ схемы (Pt для Cu-Ni отчёта) → target=PRIMARY для расчёта,
        но requested_element=Pt и element_in_schema=False — вызывающий код обязан
        предупредить, что данных по этому элементу в отчёте нет (НЕ выдавать Ni за Pt);
      • металл не упомянут вовсе → PRIMARY + element_detected=False (тоже предупреждаем)."""
    if not kpi or not kpi.strip():
        raise ValueError("KPI не задан. Без него неясно, что оптимизировать — "
                         "передайте --kpi \"...\" (например: --kpi "
                         "\"снизить потери никеля с хвостами флотации\").")
    low = kpi.lower()
    schema_symbols = tuple(schema_symbols)

    mentioned = _detect_elements(low)
    in_schema = [s for s in mentioned if s in schema_symbols]

    if in_schema:                                 # есть металл из схемы — по нему и считаем
        element, detected, elem_in_schema, requested = in_schema[0], True, True, in_schema[0]
    elif mentioned:                               # металл упомянут, но его нет в схеме отчёта
        element, detected, elem_in_schema, requested = PRIMARY_ELEMENT, True, False, mentioned[0]
    else:                                         # металл не упомянут — дефолт, но честно помечаем
        element, detected, elem_in_schema, requested = PRIMARY_ELEMENT, False, True, None

    direction = "reduce" if (any(re.search(w, low) for w in _REDUCE_WORDS)
                             and not any(re.search(w, low) for w in _INCREASE_WORDS)) else "improve"
    cons = [{"tag": tag, "kind": kind} for tag, pats, kind in _CONSTRAINTS
            if any(p in low for p in pats)]
    # запрет конкретного реагента: имя сверяется с текстом вмешательства гипотезы
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
    """Какие ограничения нарушает гипотеза (по семейству, потребности в оборудовании
    и ТЕКСТУ вмешательства — для запрета конкретного реагента).
    Только «жёсткие» (equipment/reagent); quality/throughput — цели, не штрафуются."""
    v = []
    low = (text or "").casefold()
    for c in getattr(intent, "constraints", None) or []:
        if c["kind"] == "equipment" and needs_equipment:
            v.append(c["tag"])
        elif c["kind"] == "reagent":
            name = c.get("name")
            if name:                              # запрет КОНКРЕТНОГО реагента —
                if name in low:                   # нарушение, только если он в тексте
                    v.append(c["tag"])
            elif family == REAGENT_FAMILY:        # общий запрет новых реагентов
                v.append(c["tag"])
    return v
