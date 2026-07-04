# -*- coding: utf-8 -*-
"""Обратная связь эксперта → детерминированный ре-ранк. БЕЗ ML и БЕЗ LLM.

«Обучение на фидбэке» здесь честное, не-чёрно-ящичное (организаторы прямо назвали
недетерминированный пайплайн чёрным ящиком): вердикты эксперта хранятся ЧЕЛОВЕКОЧИТАЕМЫМ
файлом outputs/feedback.json, а «обучение» = прозрачные множители к приоритету на
следующем прогоне. Тот же feedback.json → тот же ре-ранк, файл можно прочитать,
поправить руками или удалить — никаких скрытых весов.

Цикл:
  1. `python -m factory.export … --formats csv` — в CSV есть пустые колонки
     «вердикт_эксперта» / «комментарий_эксперта» (если фидбэк уже был — они
     ПРЕДЗАПОЛНЕНЫ текущим вердиктом, эксперт видит и правит, а не пишет заново);
  2. эксперт заполняет их в Excel: полезно / неверно / уже пробовали (+ комментарий);
  3. `python -m factory.feedback import <csv>` — вердикты складываются в feedback.json;
  4. следующий прогон (`python -m factory …` / flex) применяет их автоматически:
     ре-ранк + пометка на карточке HTML и в экспорте.

Это же закрывает НОВИЗНУ по определению организаторов («отличие от существующих
составов в базе»): feedback.json и есть база уже испробованных/отклонённых направлений
фабрики — гипотеза, совпавшая с «уже пробовали», честно помечается не-новой и
опускается, а не выдаётся заново как открытие. Кладбище провалов, о котором говорит
докстринг judge.py, живёт здесь.

Совпадение ищется на двух уровнях (все веса — явные константы ниже):
  exact  — та же фабрика + класс + вмешательство + элемент → полный эффект;
  family — та же фабрика + семейство + элемент → ослабленный эффект (вердикт о
           «доизмельчении -71+45» частично относится ко всему семейству раскрытия).
"""
from __future__ import annotations

import csv
import json
import os
import time

from factory.config import FEEDBACK_ENABLED, FEEDBACK_PATH

# нормализация свободного текста вердикта из Excel → канон
_VERDICT_SYNONYMS = {
    "полезно": "полезно", "хорошо": "полезно", "да": "полезно", "+": "полезно",
    "good": "полезно", "useful": "полезно", "ok": "полезно",
    "неверно": "неверно", "нет": "неверно", "ошибка": "неверно", "-": "неверно",
    "wrong": "неверно", "bad": "неверно", "невозможно": "неверно",
    "уже пробовали": "уже_пробовали", "уже_пробовали": "уже_пробовали",
    "пробовали": "уже_пробовали", "было": "уже_пробовали", "дубль": "уже_пробовали",
    "tried": "уже_пробовали", "known": "уже_пробовали",
}
# множители приоритета: {вердикт: {уровень совпадения: множитель}}. Явные и читаемые.
# «неверно» при точном совпадении — жёсткий ×0.05: приоритет ведёт impact, и лидер
# часто опережает остальных на порядок — мягкий штраф оставил бы опровергнутую
# экспертом гипотезу на первом месте. ×0.05 практически гарантирует уход в конец
# списка (но НЕ удаление — прозрачность важнее).
VERDICT_WEIGHTS = {
    "полезно":        {"exact": 1.2, "family": 1.1},
    "неверно":        {"exact": 0.05, "family": 0.5},
    "уже_пробовали":  {"exact": 0.3, "family": 0.7},
}


def _norm(s) -> str:
    return " ".join(str(s or "").split()).casefold()


def canon_verdict(raw) -> str | None:
    return _VERDICT_SYNONYMS.get(_norm(raw))


# ─────────────────────────── хранилище ───────────────────────────

def load_feedback(path: str = FEEDBACK_PATH) -> list:
    """Записи фидбэка; [] если файла нет/выключено (FACTORY_FEEDBACK=0)."""
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


# ─────────────────────────── импорт из CSV эксперта ───────────────────────────

def import_csv(csv_path: str, feedback_path: str = FEEDBACK_PATH,
               log=lambda *a: None) -> dict:
    """Прочитать CSV экспорта (см. export.py), забрать заполненные вердикты.
    Колонки ищутся ПО ИМЕНИ из шапки — перестановка столбцов в Excel не ломает импорт.
    Существующая запись с тем же ключом обновляется (новый вердикт побеждает)."""
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
                         f"factory.export --formats csv?") from None

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
            log(f"  ⚠ непонятный вердикт «{raw_verdict}» — пропущен "
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


# ─────────────────────────── применение (детерминированный ре-ранк) ───────────────────────────

def _match(h, fabric, entries):
    """Найти запись для гипотезы: сперва exact, затем family. (запись, уровень)|None."""
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
    """Применить фидбэк к гипотезам ЭТОЙ фабрики: множитель к priority + пометка на
    карточке; пересортировка и новые ранги. Возвращает число затронутых гипотез.
    Ничего не скрывает: «неверно»/«уже пробовали» опускают гипотезу, а не удаляют её."""
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
            # новизна по определению организаторов: совпадение с базой испробованных
            # направлений = не ново (см. модуль-докстринг)
            "not_novel": e["verdict"] == "уже_пробовали",
        }
        touched += 1
        log(f"  ⚑ {h.size_class}/{h.family}: {e['verdict']} ({tier}) — "
            f"приоритет ×{mult} ({old} → {h.metrics['priority']})")
    if touched:
        hyps.sort(key=lambda h: -h.metrics.get("priority", 0.0))
        for i, h in enumerate(hyps, 1):
            h.rank = i
    return touched


# ─────────────────────────── CLI ───────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="Фидбэк эксперта: импорт вердиктов из CSV экспорта → feedback.json; "
                    "следующий прогон применит их автоматически (прозрачный ре-ранк)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap_imp = sub.add_parser("import", help="забрать вердикты из CSV (factory.export)")
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
