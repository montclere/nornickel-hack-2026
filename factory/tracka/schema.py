from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class ElementSpec:
    label: str
    symbol: str
    recoverable_forms: list

@dataclass
class ReportSchema:
    name: str
    anchor_col: int = 2
    size_table_anchor: str = "Класс крупности"
    total_marker: str = "Итого"
    size_unit_marker: str = "мкм"
    mineralogy_stop_markers: tuple = ("Итого", "Извлекаемый")
    elements: list = field(default_factory=list)
    liberated_form: str | None = None
    locked_form: str | None = None
    fine_class_max_micron: float = 20.0

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
    json.dump(asdict(schema), open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
