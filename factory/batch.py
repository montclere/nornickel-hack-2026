from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import time

FORMATS_DEFAULT = "json,csv"

_SUMMARY_HEADER = ["kpi", "фабрика", "целевой_элемент", "статус", "гипотез",
                   "топ_вмешательство", "топ_класс", "impact_топ_%",
                   "потенциал_топ3_%", "фидбэк_применён", "предупреждений"]

def _slug(kpi: str, maxlen: int = 36) -> str:
    s = re.sub(r"[^0-9a-zа-яё]+", "-", kpi.casefold()).strip("-")
    return s[:maxlen].rstrip("-") or "kpi"

def read_kpi_list(path: str) -> list:
    kpis = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            kpis.append(line)
    return kpis

def collect_reports(paths) -> list:
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += glob.glob(os.path.join(p, "**", "Хвосты*.xlsx"), recursive=True)
        elif p.lower().endswith(".xlsx"):
            out.append(p)
    return sorted(set(out))

def _row(kpi, fabric, element, status, res=None, fb=0):
    hyps = (res or {}).get("hypotheses") or []
    top = hyps[0] if hyps else None
    top3 = round(sum(h.metrics.get("impact", 0) for h in hyps[:3]) * 100)
    return {
        "kpi": kpi, "фабрика": fabric, "целевой_элемент": element, "статус": status,
        "гипотез": len(hyps),
        "топ_вмешательство": top.intervention if top else "",
        "топ_класс": top.size_class if top else "",
        "impact_топ_%": round(top.metrics.get("impact", 0) * 100) if top else "",
        "потенциал_топ3_%": top3 if hyps else "",
        "фидбэк_применён": fb,
        "предупреждений": len((res or {}).get("profile").warnings) if res else "",
    }

def run_batch(kpis, reports, schema, formats=FORMATS_DEFAULT, out_dir="",
              html=False, log=lambda *a: None) -> list:
    from factory.pipeline import HypothesisFactory
    from factory.render.export import export_all
    from factory.tracka.intent import parse_intent, warn_intent

    os.makedirs(out_dir, exist_ok=True)
    summary = []
    for i, kpi in enumerate(kpis, 1):
        kdir = os.path.join(out_dir, f"kpi{i:02d}_{_slug(kpi)}")
        intent = parse_intent(kpi, schema.element_symbols())
        notes = []
        skip = warn_intent(intent, kpi, emit=notes.append,
                           schema_symbols=schema.element_symbols())
        log(f"\n[{i}/{len(kpis)}] KPI: «{kpi}»  → {kdir}")
        for n in notes:
            log("  " + n.replace("\n", " "))
        if skip:

            for path in reports:
                summary.append(_row(kpi, os.path.basename(path),
                                    intent.requested_element or "?",
                                    "элемент вне схемы — пропуск"))
            continue

        for path in reports:
            try:
                res = HypothesisFactory(path, kpi=kpi, schema=schema).run()
            except Exception as e:
                summary.append(_row(kpi, os.path.basename(path),
                                    intent.target_element, f"ошибка: {e}"))
                log(f"  ✗ {os.path.basename(path)}: {e}")
                continue
            p, hyps = res["profile"], res["hypotheses"]
            export_all(hyps, profile=p, kpi=kpi, formats=formats, out_dir=kdir)
            if html:
                open(os.path.join(kdir, f"{p.fabric}_гипотезы.html"),
                     "w", encoding="utf-8").write(res["html"])
            fb = res["tech"].get("feedback", 0)
            status = "ok" if not p.warnings else "ok, есть предупреждения парса"
            summary.append(_row(kpi, p.fabric, intent.target_element, status, res, fb))
            top = hyps[0] if hyps else None
            log(f"  ■ {p.fabric}: {len(hyps)} гипотез · топ: "
                f"{top.intervention if top else '—'}"
                + (f" · ⚑ фидбэк ×{fb}" if fb else ""))

    json.dump({"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
               "n_kpi": len(kpis), "n_reports": len(reports), "rows": summary},
              open(os.path.join(out_dir, "сводка.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "сводка.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(_SUMMARY_HEADER)
        for r in summary:
            w.writerow([r[k] for k in _SUMMARY_HEADER])
    return summary

def main():
    from factory.tracka.schema import DEFAULT_SCHEMA, load_schema

    ap = argparse.ArgumentParser(
        description="Батч-прогон набора KPI по всем фабрикам + экспорт и сводка "
                    "(детерминированно, без LLM)")
    ap.add_argument("kpi_file", help="файл со списком KPI (по одному на строку)")
    ap.add_argument("reports", nargs="+", help="Хвосты*.xlsx и/или папки с ними")
    ap.add_argument("--formats", default=FORMATS_DEFAULT,
                    help=f"форматы экспорта на каждый KPI (по умолчанию {FORMATS_DEFAULT}; "
                    "см. factory.render.export)")
    ap.add_argument("--html", action="store_true", help="писать и HTML-отчёты")
    ap.add_argument("--schema", default="", help="JSON-схема формата отчёта (опц.)")
    ap.add_argument("--out-dir", default=os.path.join("outputs", "batch"))
    args = ap.parse_args()

    if not os.path.exists(args.kpi_file):
        ap.error(f"файл со списком KPI не найден: {args.kpi_file}")
    kpis = read_kpi_list(args.kpi_file)
    if not kpis:
        ap.error(f"в {args.kpi_file} нет ни одного KPI (пустые строки и # пропускаются)")
    reports = collect_reports(args.reports)
    if not reports:
        ap.error("отчёты не найдены: передайте Хвосты*.xlsx или папки, где они лежат")
    from factory.render.export import FORMATS
    if args.formats.strip() not in ("all", ""):
        unknown = [f.strip() for f in args.formats.split(",")
                   if f.strip() and f.strip() not in FORMATS]
        if unknown:
            ap.error(f"неизвестные форматы: {', '.join(unknown)}; "
                     f"доступны: {', '.join(FORMATS)} или all")
    schema = load_schema(args.schema) if args.schema else DEFAULT_SCHEMA

    print("=" * 74)
    print(f"БАТЧ-ПРОГОН · KPI: {len(kpis)} · отчётов: {len(reports)} · "
          f"схема: {schema.name}")
    print("=" * 74)
    t0 = time.perf_counter()
    summary = run_batch(kpis, reports, schema, formats=args.formats,
                        out_dir=args.out_dir, html=args.html, log=print)

    ok = sum(1 for r in summary if r["статус"].startswith("ok"))
    skipped = sum(1 for r in summary if "вне схемы" in r["статус"])
    failed = len(summary) - ok - skipped
    print("\n" + "=" * 74)
    print(f"ИТОГО за {time.perf_counter() - t0:.2f} с: пар {len(summary)} · ok {ok} · "
          f"вне схемы {skipped} · ошибок {failed}")
    print(f"сводка: {os.path.join(args.out_dir, 'сводка.csv')} (+ сводка.json)")
    print("=" * 74)

if __name__ == "__main__":
    main()
