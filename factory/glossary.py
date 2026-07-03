# -*- coding: utf-8 -*-
"""Глоссарий метрик — отдельная HTML-страница (открывается по ссылке из отчёта)."""
from __future__ import annotations

ENTRIES = [
    ("Тоннаж извлекаемого металла", "ФАКТ из отчёта.",
     "Сумма тонн Ni/Cu в извлекаемых формах (раскрытый + закрытый Pnt/Cp + миллерит) "
     "по классу. Берётся напрямую из ячеек Excel, ничего не оценивается."),
    ("impact — масштаб потери", "0..1.",
     "Доля извлекаемых потерь класса от всех извлекаемых потерь фабрики. "
     "impact = извлекаемые_тонны_класса / сумма_по_всем_классам. Ведёт ранжирование."),
    ("addressability — «излечимость»", "0..1.",
     "Какая часть ВСЕХ потерь класса вообще извлекаема текущей технологией. "
     "addressability = извлекаемые_тонны / все_тонны_класса. Высокая — почти всё чинится."),
    ("clarity — ясность механизма", "0..1. Научная метрика.",
     "Доминирование одной извлекаемой формы среди извлекаемых. "
     "clarity = тонны_главной_формы / извлекаемые_тонны. Чем выше, тем однозначнее "
     "гипотеза (один чёткий механизм, легче проверить)."),
    ("feasibility — реализуемость", "0.6 или 1.0.",
     "1.0 — вмешательство без нового оборудования; 0.6 — требует оборудования. "
     "Задаётся правилом диагноза (rules.py)."),
    ("confidence — достоверность", "0.3 / 0.6 / 1.0.",
     "Полнота данных под классом: есть ли минералогия и не битые ли числа (#REF!)."),
    ("priority — приоритет", "произведение, 0..1.",
     "priority = impact · (0.5 + 0.5·addressability) · feasibility · confidence. "
     "Масштаб ведёт, излечимость модулирует. По нему сортируются гипотезы."),
    ("Кривая раскрытия", "график.",
     "Доли закрытого/раскрытого Pnt по классам крупности. Показывает «обрыв раскрытия» — "
     "границу крупности, ниже которой минерал раскрывается измельчением."),
    ("Форм-разбивка", "таблица.",
     "Куда физически уходит Ni по минеральным формам. Часть форм (силикаты/валлериит, "
     "примесь в пирротине) — физически НЕ извлекаемы: это честный потолок."),
    ("FAMILY-COVERAGE (в бенчмарке)", "оценка.",
     "Наши вмешательства и эталонные гипотезы инженеров классифицируются в семейства "
     "(измельчение / классификация / грохочение / флотация / реагенты). Coverage = доля "
     "эталонных, чьё семейство встретилось у нас. Это НЕ дословное совпадение, а «попали "
     "ли в тот же КЛАСС вмешательства»; вмешательства выведены из данных, не подсказаны."),
]


def render():
    rows = "".join(
        f'<div class="e"><div class="term">{t} <span class="rng">{r}</span></div>'
        f'<div class="d">{d}</div></div>' for t, r, d in ENTRIES)
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Глоссарий метрик</title>
<style>
body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#12303f;
  background:linear-gradient(180deg,#e7f3fa,#eef6fb);line-height:1.55}}
.wrap{{max-width:760px;margin:0 auto;padding:38px 22px 70px}}
h1{{font-size:25px;font-weight:800;margin:0 0 4px}} h1 span{{color:#12b3ab}}
.sub{{color:#5f7d8c;font-size:13.5px;margin-bottom:20px}}
.e{{background:#fff;border:1px solid #e6eef3;border-radius:14px;padding:14px 18px;margin:0 0 12px;
  box-shadow:0 2px 10px rgba(31,122,224,.05)}}
.term{{font-weight:700;font-size:15px}} .rng{{color:#9db3bf;font-weight:500;font-size:12px;margin-left:6px}}
.d{{color:#37505c;font-size:13.5px;margin-top:4px}}
a{{color:#1f7ae0;text-decoration:none;font-size:13px}}
</style></head><body><div class="wrap">
  <a href="javascript:history.back()">← назад к отчёту</a>
  <h1>Глоссарий <span>метрик</span></h1>
  <div class="sub">всё считается детерминированно из ячеек отчёта, без LLM и без цен</div>
  {rows}
</div></body></html>"""


def write(out_dir):
    import os
    path = os.path.join(out_dir, "glossary.html")
    open(path, "w", encoding="utf-8").write(render())
    return path
