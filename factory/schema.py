# -*- coding: utf-8 -*-
"""Схема отчёта — ВСЁ формат-специфичное знание, вынесенное из reader.py/rules.py.

Смена формата отчёта = другая ReportSchema (JSON-файл или объект), КОД (reader.py,
rules.py, analysis.py) НЕ МЕНЯЕТСЯ — он читает схему, а не хардкодит её.

DEFAULT_SCHEMA — известный формат отчёта института по хвостам (флотация Cu-Ni). Это
не хардкод логики, а конфиг с данными, который логика интерпретирует. Схему для
НОВОГО формата отчёта можно (а) написать/отредактировать вручную — обычный JSON,
человек читает и правит; или (б) предложить через LLM ОДНОРАЗОВО (см.
schema_bootstrap.py) — после сохранения схемы в файл всё дальнейшее чтение и
рассуждение снова полностью детерминированы, LLM в цикле парсинга нет.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class ElementSpec:
    label: str              # подпись элемента в отчёте, напр. «Элемент 28»
    symbol: str              # каноническое имя для остальной системы, напр. «Ni»
    recoverable_forms: list  # минеральные формы, извлекаемые ТЕКУЩЕЙ технологией


@dataclass
class ReportSchema:
    name: str
    anchor_col: int = 2                              # колонка подписей-якорей (B)
    size_table_anchor: str = "Класс крупности"        # подпись, открывающая таблицу классов
    total_marker: str = "Итого"                       # маркер конца таблицы/блока
    size_unit_marker: str = "мкм"                     # единица в подписи класса крупности
    mineralogy_stop_markers: tuple = ("Итого", "Извлекаемый")  # конец блока минералогии
    elements: list = field(default_factory=list)      # list[ElementSpec]
    liberated_form: str | None = None                 # «раскрытый» минерал (сросток раскрыт)
    locked_form: str | None = None                     # «закрытый» минерал (заперт в сростке)
    fine_class_max_micron: float = 20.0                # порог «тонкий класс» (шламы) в мкм

    def element_symbols(self) -> tuple:
        return tuple(e.symbol for e in self.elements)

    def primary_element(self) -> str | None:
        return self.elements[0].symbol if self.elements else None

    def is_recoverable(self, symbol: str, form: str) -> bool:
        spec = next((e for e in self.elements if e.symbol == symbol), None)
        return bool(spec) and form in spec.recoverable_forms


DEFAULT_SCHEMA = ReportSchema(
    name="tailings_institute_cu_ni_v1",
    elements=[
        ElementSpec(label="Элемент 28", symbol="Ni",
                   recoverable_forms=["Раскрытый Pnt/Cp", "Закрытый Pnt/Cp", "Миллерит"]),
        ElementSpec(label="Элемент 29", symbol="Cu",
                   recoverable_forms=["Раскрытый Pnt/Cp", "Закрытый Pnt/Cp"]),
    ],
    liberated_form="Раскрытый Pnt/Cp", locked_form="Закрытый Pnt/Cp",
)


def load_schema(path: str) -> ReportSchema:
    d = json.load(open(path, encoding="utf-8"))
    d["elements"] = [ElementSpec(**e) for e in d.get("elements", [])]
    if "mineralogy_stop_markers" in d:
        d["mineralogy_stop_markers"] = tuple(d["mineralogy_stop_markers"])
    return ReportSchema(**d)


def save_schema(schema: ReportSchema, path: str) -> None:
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(asdict(schema), open(path, "w", encoding="utf-8"),  # asdict рекурсивно
              ensure_ascii=False, indent=2)                       # разворачивает ElementSpec
