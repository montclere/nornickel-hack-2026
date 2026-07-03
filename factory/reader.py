# -*- coding: utf-8 -*-
"""Чтение отчёта по хвостам → структурированный профиль потерь. ДЕТЕРМИНИРОВАННО.

Никакого LLM. Только парсинг Excel по стабильным подписям-якорям (openpyxl).
Один и тот же файл → один и тот же профиль (побайтово).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from openpyxl import load_workbook

# --- доменные константы (из инструкции «Как читать отчёт института по хвостам») ---
ELEMENTS = {"Элемент 28": "Ni", "Элемент 29": "Cu"}
# потенциально извлекаемые текущей технологией минеральные формы
RECOVERABLE = {
    "Ni": {"Раскрытый Pnt/Cp", "Закрытый Pnt/Cp", "Миллерит"},
    "Cu": {"Раскрытый Pnt/Cp", "Закрытый Pnt/Cp"},
}
LIBERATED = "Раскрытый Pnt/Cp"   # раскрытый минерал
LOCKED = "Закрытый Pnt/Cp"       # заперт в сростках
SIZE_ORDER = ["+125", "-125+71", "-71+45", "-45+20", "-20+10", "-10"]


def _num(v):
    return v if isinstance(v, (int, float)) else None


def _norm_class(label: str) -> str:
    """«-71 + 45 мкм», « -71 +45» → «-71+45» (канон, без пробелов).

    Подписи класса в таблице и в блоках минералогии расходятся по пробелам —
    убираем все пробелы, чтобы одно и то же читалось одинаково."""
    s = re.sub(r"мкм", "", str(label))
    return re.sub(r"\s+", "", s)


@dataclass
class FormLoss:
    """Потеря элемента в конкретной минеральной форме внутри класса крупности."""
    form: str
    element: str
    tonnes: float
    pct: float
    recoverable: bool
    cell: str


@dataclass
class ClassLoss:
    """Потери по классу крупности."""
    size_class: str
    tonnes: dict = field(default_factory=dict)      # {"Ni": т, "Cu": т}
    cells: dict = field(default_factory=dict)        # провенанс {"Ni": "E200"}
    forms: list = field(default_factory=list)        # list[FormLoss]

    def recoverable_tonnes(self, element: str) -> float:
        return round(sum(f.tonnes for f in self.forms
                         if f.element == element and f.recoverable), 1)

    def dominant_recoverable_form(self, element: str) -> str | None:
        cand = [f for f in self.forms if f.element == element and f.recoverable]
        return max(cand, key=lambda f: f.tonnes).form if cand else None


@dataclass
class TailingsProfile:
    fabric: str
    elements: dict = field(default_factory=dict)     # {"Ni": {"grade": .., "cell": ..}}
    classes: list = field(default_factory=list)      # list[ClassLoss], в порядке крупности
    source: str = ""
    warnings: list = field(default_factory=list)     # сигналы «парс мог сбиться»

    def by_class(self, sc: str) -> ClassLoss | None:
        return next((c for c in self.classes if c.size_class == sc), None)


class TailingsReader:
    """Парсер отчёта по хвостам. Секция «отвальные хвосты общие» (итоговые потери)."""

    def __init__(self, path: str):
        self.path = path
        self.fabric = re.sub(r"Хвосты\s*|\.xlsx|_\d+", "", path.split("/")[-1]).strip()

    def read(self) -> TailingsProfile:
        ws = load_workbook(self.path, data_only=True).active
        grid = {(c.row, c.column): c.value for row in ws.iter_rows() for c in row
                if c.value is not None}
        prof = TailingsProfile(fabric=self.fabric, source=self.path.split("/")[-1])

        # --- секция: берём ПОСЛЕДНЮЮ таблицу «Класс крупности» (отвальные общие) ---
        hdr_rows = sorted(r for (r, col), v in grid.items()
                          if col == 2 and "Класс крупности" in str(v))
        if not hdr_rows:
            prof.warnings.append("не найден якорь «Класс крупности» — формат не распознан "
                                 "(другой отчёт? сменились подписи?). Профиль пуст.")
            return prof
        start = hdr_rows[-1]

        # колонки: C=доля класса, D=%Ni, E=т Ni, F=%Cu, G=т Cu
        ecol = {"Ni": (4, 5), "Cu": (6, 7)}  # (pct_col, tonnes_col)

        # --- таблица классов крупности ---
        r = start + 1
        classes: dict[str, ClassLoss] = {}
        while r < start + 12:
            b = grid.get((r, 2))
            if b is None:
                r += 1; continue
            if str(b).startswith("Итого"):
                break
            sc = _norm_class(b)
            cl = ClassLoss(size_class=sc)
            for el, (_, tcol) in ecol.items():
                cl.tonnes[el] = _num(grid.get((r, tcol)))
                cl.cells[el] = f"{chr(64+tcol)}{r}"
            classes[sc] = cl
            r += 1

        # --- блоки минералогии по классам (ниже таблицы, до конца листа) ---
        for (row, col), v in sorted(grid.items()):
            if col != 2 or row <= start:
                continue
            s = str(v)
            if "мкм" not in s or "Итого" in s:
                continue
            sc = _norm_class(s)
            if sc not in classes:
                continue
            self._read_mineralogy(grid, row, classes[sc], ecol)

        prof.classes = [classes[sc] for sc in SIZE_ORDER if sc in classes]
        self._validate(prof)
        return prof

    def _validate(self, prof: TailingsProfile):
        """Страховка: ловим признаки сбитого парса, чтобы не выдавать уверенную чушь."""
        if len(prof.classes) < 4:
            prof.warnings.append(
                f"распознано лишь {len(prof.classes)} классов крупности (ожидалось ~6) — "
                "возможно, съехал формат или колонки.")
        for cl in prof.classes:
            forms_t = sum(f.tonnes for f in cl.forms if f.element == "Ni")
            class_t = cl.tonnes.get("Ni") or 0.0
            # баланс: сумма тонн по формам класса ≈ тоннам класса (±25%)
            if class_t and forms_t and abs(forms_t - class_t) / class_t > 0.25:
                prof.warnings.append(
                    f"класс {cl.size_class}: сумма форм {forms_t:.0f} т ≠ итогу класса "
                    f"{class_t:.0f} т (>25%) — проверьте раскладку колонок.")
            rec = cl.recoverable_tonnes("Ni")
            if class_t and rec > class_t * 1.02:
                prof.warnings.append(
                    f"класс {cl.size_class}: извлекаемого ({rec:.0f} т) больше всего "
                    f"металла класса ({class_t:.0f} т) — раскладка сбита.")

    def _read_mineralogy(self, grid, header_row, cl: ClassLoss, ecol):
        """Прочитать формы блока: строки от header+1 до «Итого»."""
        forms_seen = {f.form + f.element for f in cl.forms}  # анти-дубли между секциями
        r = header_row + 1
        while r < header_row + 12:
            b = grid.get((r, 2))
            if b is None:
                r += 1; continue
            name = str(b).strip()
            if name.startswith("Итого") or "Извлекаемый" in name:
                break
            for el, (pcol, tcol) in ecol.items():
                t = _num(grid.get((r, tcol)))
                p = _num(grid.get((r, pcol)))
                if t is None and p is None:
                    continue
                key = name + el
                if key in forms_seen:
                    continue
                cl.forms.append(FormLoss(
                    form=name, element=el, tonnes=t or 0.0, pct=p or 0.0,
                    recoverable=(name in RECOVERABLE[el]),
                    cell=f"{chr(64+tcol)}{r}"))
                forms_seen.add(key)
            r += 1
