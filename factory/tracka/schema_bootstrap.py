from __future__ import annotations

import argparse
import os

from factory.ext.llm import Yandex, extract_json
from factory.tracka.schema import ElementSpec, ReportSchema, save_schema

SYSTEM = ("Ты — инженер данных. Смотришь на подписи (не данные) незнакомого отчёта по "
          "обогащению руды и предлагаешь схему для его парсинга. Ничего не выдумываешь "
          "сверх того, что явно следует из подписей. Ответ — ТОЛЬКО JSON.")

PROMPT = """Вот все текстовые подписи из колонки-якоря (B) незнакомого Excel-отчёта
по хвостам обогащения, в порядке появления:

{labels}

Определи по ним:
1. "size_table_anchor" — подпись, которая открывает таблицу классов крупности
   (обычно содержит слова «класс», «крупност»).
2. "total_marker" — слово, которым помечаются итоговые/суммарные строки (обычно «Итого»).
3. "elements" — список элементов отчёта: каждый — объект {{"label": подпись элемента
   как в файле, "symbol": короткое общепринятое имя (Ni/Cu/Fe/Au/Ag/...),
   "recoverable_forms": список подписей минеральных форм из текста, которые похожи
   на извлекаемые (обычно «раскрытый», рядом с именем минерала, НЕ «примесь»/
   «силикат»/«пирит» — те обычно неизвлекаемы).
4. "liberated_form" — подпись формы, означающей «раскрытый минерал» (если есть).
5. "locked_form" — подпись формы, означающей «заперт в сростках/закрытый» (если есть).

Верни ТОЛЬКО JSON:
{{"size_table_anchor":"...","total_marker":"...","elements":[{{"label":"...","symbol":"...",
"recoverable_forms":["..."]}}],"liberated_form":"...","locked_form":"..."}}"""

def _scan_labels(path: str, anchor_col: int = 2, limit: int = 400) -> list:
    from openpyxl import load_workbook
    ws = load_workbook(path, data_only=True, read_only=True).active
    labels, seen = [], set()
    for row in ws.iter_rows(min_col=anchor_col, max_col=anchor_col):
        for c in row:
            v = c.value
            if v is None:
                continue
            s = str(v).strip()
            if s and s not in seen:
                seen.add(s); labels.append(s)
            if len(labels) >= limit:
                return labels
    return labels

def _infer_units(labels) -> tuple:
    joined = " ".join(labels).lower()
    if "мкм" in joined or "µm" in joined or "мк" in joined:
        return "мкм", 20.0
    if "мм" in joined or (" mm" in joined) or joined.endswith("mm"):
        return "мм", 0.02
    if "mesh" in joined or "меш" in joined:
        return "mesh", 200.0
    return "мкм", 20.0

def propose_schema(path: str, llm=None, name: str | None = None) -> ReportSchema:
    llm = llm or Yandex(temperature=0.0)
    if not llm.ready:
        raise RuntimeError("нет ключа Yandex (.env) — бутстрап схемы требует LLM "
                           "(альтернатива: написать схему вручную, см. schema.py)")
    labels = _scan_labels(path)
    raw = llm.complete(SYSTEM, PROMPT.format(labels="\n".join(labels)))
    d = extract_json(raw)
    if not isinstance(d, dict):
        raise RuntimeError(f"LLM не вернул валидный JSON-схему: {raw[:300]}")

    elements = [ElementSpec(label=e.get("label", ""), symbol=e.get("symbol", ""),
                            recoverable_forms=list(e.get("recoverable_forms", [])))
               for e in d.get("elements", []) if e.get("label") and e.get("symbol")]
    unit_marker, fine_max = _infer_units(labels)
    return ReportSchema(
        name=name or f"bootstrapped_{os.path.splitext(os.path.basename(path))[0]}",
        size_table_anchor=d.get("size_table_anchor") or "Класс крупности",
        total_marker=d.get("total_marker") or "Итого",
        size_unit_marker=unit_marker, fine_class_max_micron=fine_max,
        elements=elements,
        liberated_form=d.get("liberated_form"), locked_form=d.get("locked_form"))

def main():
    ap = argparse.ArgumentParser(
        description="Предложить схему парсинга для незнакомого формата отчёта (LLM, одноразово)")
    ap.add_argument("report", help="путь к незнакомому Excel-отчёту")
    ap.add_argument("--out", default="", help="куда сохранить схему (по умолчанию рядом со схемами)")
    args = ap.parse_args()

    print("=" * 74)
    print("БУТСТРАП СХЕМЫ (LLM смотрит ТОЛЬКО на подписи, не на данные, один раз)")
    print("=" * 74)
    schema = propose_schema(args.report)
    out = args.out or os.path.join("outputs", "schemas", f"{schema.name}.json")
    save_schema(schema, out)
    print(f"схема предложена и сохранена: {out}")
    print(f"  элементы: {[(e.label, e.symbol) for e in schema.elements]}")
    print(f"  раскрытая форма: {schema.liberated_form} | закрытая: {schema.locked_form}")

    print("\nВнимание: Это ПРЕДЛОЖЕНИЕ, не факт: LLM классифицирует подписи файла, а не")
    print("  извлекает дословный факт (цитатный гейт тут неприменим). Проверьте файл")
    print(f"  схемы ({out}) перед боевым использованием.")

    print("\nАвтопроверка: пробую распарсить отчёт этой схемой и смотрю на баланс...")
    from factory.tracka.reader import TailingsReader
    prof = TailingsReader(args.report, schema=schema).read()
    if prof.warnings:
        print("  Внимание: схема ДАЛА ПРЕДУПРЕЖДЕНИЯ при пробном парсинге — вероятно, неточна:")
        for w in prof.warnings:
            print(f"    · {w}")
    else:
        print(f"  ✓ пробный парсинг чист: {len(prof.classes)} классов крупности, "
              f"баланс форм сходится — схема выглядит рабочей.")
    print("\nПосле этого шага дальнейшие прогоны с данной схемой полностью")
    print("детерминированы (--schema " + out + "), LLM в парсинге больше не участвует.")

if __name__ == "__main__":
    main()
