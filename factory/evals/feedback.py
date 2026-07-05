from __future__ import annotations

import csv
import json
import os
import time

from factory.config import FEEDBACK_ENABLED, FEEDBACK_PATH

_VERDICT_SYNONYMS = {
    "полезно": "полезно", "хорошо": "полезно", "да": "полезно", "+": "полезно",
    "good": "полезно", "useful": "полезно", "ok": "полезно",
    "неверно": "неверно", "нет": "неверно", "ошибка": "неверно", "-": "неверно",
    "wrong": "неверно", "bad": "неверно", "невозможно": "неверно",
    "уже пробовали": "уже_пробовали", "уже_пробовали": "уже_пробовали",
    "пробовали": "уже_пробовали", "было": "уже_пробовали", "дубль": "уже_пробовали",
    "tried": "уже_пробовали", "known": "уже_пробовали",
}

VERDICT_WEIGHTS = {
    "полезно":        {"exact": 1.2, "family": 1.1},
    "неверно":        {"exact": 0.05, "family": 0.5},
    "уже_пробовали":  {"exact": 0.3, "family": 0.7},
}

def _norm(s) -> str:
    return " ".join(str(s or "").split()).casefold()

def canon_verdict(raw) -> str | None:
    return _VERDICT_SYNONYMS.get(_norm(raw))

def load_feedback(path: str = FEEDBACK_PATH) -> list:
    if not FEEDBACK_ENABLED or not (path and os.path.exists(path)):
        return []
    try:
        d = json.load(open(path, encoding="utf-8"))
        return list(d.get("entries") or [])
    except (json.JSONDecodeError, OSError):
        return []

def save_feedback(entries: list, path: str = FEEDBACK_PATH) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump({"version": 1, "entries": entries}, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return path

def _key(e) -> tuple:
    return tuple(_norm(e.get(k)) for k in
                 ("fabric", "size_class", "family", "intervention", "target_element"))

def upsert(entry: dict, path: str = FEEDBACK_PATH) -> dict:
    verdict = canon_verdict(entry.get("verdict"))
    if verdict is None:
        raise ValueError(f"непонятный вердикт «{entry.get('verdict')}» "
                         f"(допустимо: полезно / неверно / уже пробовали)")
    e = {k: str(entry.get(k, "")).strip() for k in
         ("fabric", "size_class", "family", "intervention", "target_element", "note")}
    e["verdict"] = verdict
    e["imported_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    entries = load_feedback(path)
    for old in entries:
        if _key(old) == _key(e):
            old.update(e)
            break
    else:
        entries.append(e)
    save_feedback(entries, path)
    return e

def remove(entry: dict, path: str = FEEDBACK_PATH) -> bool:
    entries = load_feedback(path)
    k = _key(entry)
    kept = [e for e in entries if _key(e) != k]
    if len(kept) == len(entries):
        return False
    save_feedback(kept, path)
    return True

def find_saved(hyp: dict, path: str = FEEDBACK_PATH) -> dict | None:
    k = _key(hyp)
    return next((e for e in load_feedback(path) if _key(e) == k), None)

def import_csv(csv_path: str, feedback_path: str = FEEDBACK_PATH,
               log=lambda *a: None) -> dict:
    rows = list(csv.reader(open(csv_path, encoding="utf-8-sig"), delimiter=";"))
    if not rows:
        raise ValueError(f"пустой CSV: {csv_path}")
    head = [h.strip() for h in rows[0]]
    need = ["фабрика", "класс", "семейство", "вмешательство", "целевой_элемент",
            "вердикт_эксперта", "комментарий_эксперта"]
    try:
        idx = {name: head.index(name) for name in need}
    except ValueError as e:
        raise ValueError(f"в CSV нет ожидаемой колонки ({e}); это файл из "
                         f"factory.render.export --formats csv?") from None

    entries = load_feedback(feedback_path)
    by_key = {_key(e): e for e in entries}
    stats = {"added": 0, "updated": 0, "empty": 0, "unknown_verdict": 0}
    for row in rows[1:]:
        if len(row) < len(head):
            continue
        raw_verdict = row[idx["вердикт_эксперта"]].strip()
        if not raw_verdict:
            stats["empty"] += 1
            continue
        verdict = canon_verdict(raw_verdict)
        if verdict is None:
            stats["unknown_verdict"] += 1
            log(f"  Внимание: непонятный вердикт «{raw_verdict}» — пропущен "
                f"(допустимо: полезно / неверно / уже пробовали)")
            continue
        e = {"fabric": row[idx["фабрика"]].strip(),
             "size_class": row[idx["класс"]].strip(),
             "family": row[idx["семейство"]].strip(),
             "intervention": row[idx["вмешательство"]].strip(),
             "target_element": row[idx["целевой_элемент"]].strip(),
             "verdict": verdict,
             "note": row[idx["комментарий_эксперта"]].strip(),
             "imported_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        k = _key(e)
        if k in by_key:
            by_key[k].update(e); stats["updated"] += 1
        else:
            by_key[k] = e; entries.append(e); stats["added"] += 1
    save_feedback(entries, feedback_path)
    return stats

def _match(h, fabric, entries):
    hf = _norm(fabric)
    exact = (hf, _norm(h.size_class), _norm(h.family),
             _norm(h.intervention), _norm(h.target_element))
    fam = (hf, _norm(h.family), _norm(h.target_element))
    fam_hit = None
    for e in entries:
        if _key(e) == exact:
            return e, "exact"
        if fam_hit is None and (_norm(e.get("fabric")), _norm(e.get("family")),
                                _norm(e.get("target_element"))) == fam:
            fam_hit = e
    return (fam_hit, "family") if fam_hit else None

def apply_feedback(hyps, fabric: str, entries: list | None = None,
                   log=lambda *a: None) -> int:
    entries = load_feedback() if entries is None else entries
    if not entries or not hyps:
        return 0
    touched = 0
    for h in hyps:
        hit = _match(h, fabric, entries)
        if not hit:
            continue
        e, tier = hit
        mult = VERDICT_WEIGHTS[e["verdict"]][tier]
        old = h.metrics.get("priority", 0.0)
        h.metrics["priority"] = round(old * mult, 5)
        h.expert_feedback = {
            "verdict": e["verdict"], "note": e.get("note", ""),
            "tier": tier, "multiplier": mult,

            "not_novel": e["verdict"] == "уже_пробовали",
        }
        touched += 1
        log(f"  {h.size_class}/{h.family}: {e['verdict']} ({tier}) — "
            f"приоритет ×{mult} ({old} → {h.metrics['priority']})")
    if touched:
        hyps.sort(key=lambda h: -h.metrics.get("priority", 0.0))
        for i, h in enumerate(hyps, 1):
            h.rank = i
    return touched

def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="Фидбэк эксперта: импорт вердиктов из CSV экспорта → feedback.json; "
                    "следующий прогон применит их автоматически (прозрачный ре-ранк)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap_imp = sub.add_parser("import", help="забрать вердикты из CSV (factory.render.export)")
    ap_imp.add_argument("csv", help="CSV с заполненными колонками вердикт/комментарий")
    ap_imp.add_argument("--feedback", default=FEEDBACK_PATH)
    ap_list = sub.add_parser("list", help="показать текущую базу фидбэка")
    ap_list.add_argument("--feedback", default=FEEDBACK_PATH)
    args = ap.parse_args()

    if args.cmd == "import":
        stats = import_csv(args.csv, args.feedback, log=print)
        print(f"импорт: новых {stats['added']}, обновлено {stats['updated']}, "
              f"без вердикта {stats['empty']}, непонятных {stats['unknown_verdict']}")
        print(f"база фидбэка: {args.feedback} (человекочитаемый JSON — можно править руками)")
        print("применится автоматически при следующем прогоне factory / factory.flex")
    elif args.cmd == "list":
        entries = load_feedback(args.feedback)
        if not entries:
            print(f"база фидбэка пуста ({args.feedback})"); return
        for e in entries:
            print(f"  [{e['verdict']:<14}] {e['fabric']} · {e['size_class']} · "
                  f"{e['intervention']}" + (f" — «{e['note']}»" if e.get("note") else ""))
        print(f"всего: {len(entries)} записей · {args.feedback}")

if __name__ == "__main__":
    main()
