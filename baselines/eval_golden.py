#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GOLDEN-EVAL · сравнение выданных гипотез с эталонным набором организаторов.

Организаторы дали «золотой» набор — гипотезы мозгового штурма инженеров
(`Гипотезы*.docx`). Здесь мы измеряем, насколько автоматически сгенерированные
гипотезы (hypotheses.json из основного пайплайна) их покрывают — по семантической
близости эмбеддингов (детерминированно, без ручной разметки).

Метрики:
  - для каждой эталонной гипотезы — лучший матч среди наших (макс. косинус);
  - COVERAGE@thr — доля эталонных, у которых есть наш матч выше порога;
  - средний best-cosine.

Запуск:
    uv run python eval_golden.py --pred A_grounded_generation/hypotheses.json \\
        --golden "путь/к/Гипотезы ТОФ.docx" --thr 0.6

Зависимости: stdlib + common.llm (эмбеддинги Yandex).
"""
from __future__ import annotations

import argparse
import glob
import html
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common.llm import Yandex, cosine, extract_json  # noqa: E402


def read_docx_lines(path):
    if not path.lower().endswith(".docx"):
        raise SystemExit(f"golden должен быть .docx с эталонными гипотезами "
                         f"(не {os.path.splitext(path)[1]}). Это файл «Гипотезы *.docx», "
                         f"а не «Хвосты *.xlsx».")
    z = zipfile.ZipFile(path)
    if "word/document.xml" not in z.namelist():
        raise SystemExit(f"{path} — не похоже на Word-документ.")
    xml = z.read("word/document.xml").decode("utf-8", "ignore")
    text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml)))
    return [l.strip(" .0123456789") for l in text.splitlines()
            if len(l.strip()) > 8 and "мозгов" not in l.lower()]


def pred_full(path):
    """Наши гипотезы целиком (для судьи): if/then/because + факты-источники."""
    data = json.load(open(path, encoding="utf-8"))
    out = []
    for h in data:
        srcs = "; ".join(f.get("locator", "") for f in h.get("facts", []))
        out.append({"if": h.get("if", ""), "then": h.get("then", ""),
                    "because": h.get("because", ""), "sources": srcs})
    return out


def pred_texts(path):
    data = json.load(open(path, encoding="utf-8"))
    return [f"{h.get('if','')} {h.get('then','')}".strip() for h in data]


JUDGE_SYSTEM = (
    "Ты — главный технолог обогатительной фабрики, беспристрастный эксперт. Оцениваешь "
    "СГЕНЕРИРОВАННЫЕ гипотезы относительно ЭТАЛОННОГО набора инженеров, по смыслу "
    "(не по словам). Ответ — ТОЛЬКО КОМПАКТНЫЙ JSON в одну строку, без Markdown, "
    "без лишних пробелов и переносов."
)
JUDGE_PROMPT = """ЭТАЛОН (пронумерован):
{golden}

НАШИ гипотезы (пронумерованы):
{pred}

Верни ТОЛЬКО компактный JSON (по индексам, без повтора текста):
{{"coverage":[{{"g":<номер эталона>,"status":"covered|partial|missed","by":<номер нашей или -1>}}, ...для каждого эталона...],
"quality":{{"specificity":0..1,"testability":0..1,"relevance":0..1,"grounding":0..1}},
"extra_useful":[<номера наших вне эталона>],
"verdict":"хуже|сопоставимо|лучше",
"reasoning":"1-2 предложения"}}
grounding оценивай по привязке гипотезы к конкретным данным/классу крупности."""


def llm_judge(golden, preds, llm):
    gtxt = "\n".join(f"{i+1}. {g}" for i, g in enumerate(golden))
    ptxt = "\n".join(
        f"[{i}] ЕСЛИ {p['if']} — ТО {p['then']} (ПЧ: {p['because'][:120]}; "
        f"источники: {p['sources'][:80]})" for i, p in enumerate(preds))
    raw = llm.complete(JUDGE_SYSTEM, JUDGE_PROMPT.format(golden=gtxt, pred=ptxt))
    return extract_json(raw), raw


# семейства инженерных вмешательств (общие для обогащения) → ключевые слова
FAMILIES = {
    "измельчение/раскрытие": ["футеровк", "мельниц", "измельч", "доизмельч", "раскрыт",
                              "гранулометри", "дроб", "шар"],
    "классификация": ["классифик", "гидроцикл", "циклон", "насадк", "классификатор",
                      "возвратн"],
    "грохочение": ["грохот", "грохочен", "сито", "ситов"],
    "флотация-схема": ["флотац", "контактн", "чан", "время флотац", "перечист",
                       "контрольн", "фронт", "возврат в голов", "агитац", "плотност"],
    "реагенты": ["реагент", "собират", "ксантоген", "депрессор", "кмц", " ph", "подавл",
                 "активац", "купорос"],
}


def family_of(text):
    low = " " + text.lower()
    best, score = None, 0
    for fam, kws in FAMILIES.items():
        s = sum(low.count(k) for k in kws)
        if s > score:
            best, score = fam, s
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", default=os.path.join(os.path.dirname(__file__),
                    "A_grounded_generation", "hypotheses.json"))
    ap.add_argument("--golden", default="")
    ap.add_argument("--thr", type=float, default=0.6)
    ap.add_argument("--no-judge", action="store_true", help="без LLM-судьи")
    args = ap.parse_args()

    if not args.golden:
        here = os.path.dirname(os.path.abspath(__file__))
        roots = [here, os.path.dirname(here)]  # baselines + репозиторий (incl. task/)
        cands = []
        for r in roots:
            cands += glob.glob(os.path.join(r, "**", "Гипотезы*.docx"), recursive=True)
        cands = sorted(set(cands))
        if not cands:
            print("Не найден golden docx (Гипотезы*.docx). Укажите --golden путь"); return
        print("Найдены эталонные наборы:")
        for c in cands:
            print(f"  - {c}")
        args.golden = cands[0]
        print(f"→ использую первый: {os.path.basename(args.golden)} "
              f"(выберите нужный через --golden)\n")

    preds = pred_texts(args.pred)
    golden = read_docx_lines(args.golden)
    print("=" * 78)
    print("GOLDEN-EVAL")
    print(f"наши гипотезы: {len(preds)} ({os.path.basename(args.pred)})")
    print(f"эталон: {len(golden)} ({os.path.basename(args.golden)})")
    print("=" * 78)

    llm = Yandex(temperature=0.2, max_tokens=3500)
    if not llm.ready:
        print("Нет ключа Yandex (.env) — эмбеддинги недоступны."); return
    pe = [llm.embed(p, kind="doc") for p in preds]
    ge = [llm.embed(g, kind="query") for g in golden]

    hits, sims = 0, []
    print("\nПокрытие эталонных гипотез (лучший наш матч):")
    for g, gv in zip(golden, ge):
        best, bi = -1.0, -1
        for i, pv in enumerate(pe):
            c = cosine(gv, pv)
            if c > best:
                best, bi = c, i
        sims.append(best)
        mark = "✓" if best >= args.thr else "·"
        if best >= args.thr:
            hits += 1
        print(f"  {mark} cos={best:.2f}  ЭТАЛОН: {g[:52]}")
        print(f"        ← наш:  {preds[bi][:60] if bi>=0 else '—'}")

    cov = hits / len(golden) if golden else 0
    avg = sum(sims) / len(sims) if sims else 0
    print("\n" + "-" * 78)
    print(f"COVERAGE@{args.thr} (дословный косинус) = {hits}/{len(golden)} = {cov:.0%}   "
          f"| средний best-cosine = {avg:.2f}")

    # ── честная метрика: совпадение по СЕМЕЙСТВУ вмешательства ──
    pred_fams = {family_of(p) for p in preds} - {None}
    gold_fams = [family_of(g) for g in golden]
    fam_hit = sum(1 for f in gold_fams if f in pred_fams)
    matched = sum(1 for f in gold_fams if f is not None)
    print("\nПо СЕМЕЙСТВУ вмешательства (устойчиво к формулировке):")
    print(f"  наши семейства: {sorted(pred_fams) or '—'}")
    for g, f in zip(golden, gold_fams):
        mark = "✓" if f in pred_fams else "·"
        print(f"  {mark} [{f or 'не распознано':<22}] {g[:44]}")
    fam_cov = fam_hit / len(golden) if golden else 0
    print(f"\nFAMILY-COVERAGE = {fam_hit}/{len(golden)} = {fam_cov:.0%} "
          f"(из распознанных: {fam_hit}/{matched})")
    print("=" * 78)
    print("Косинус недооценивает совпадения «то же вмешательство, другие слова»")
    print("(«футеровка мельниц» vs «увеличить измельчение» — одно семейство, cos низкий).")
    print("Family-coverage — честная мера: попали ли мы в нужный КЛАСС вмешательства.")

    # ── LLM-СУДЬЯ: качественная оценка по смыслу (не по словам) ──
    if not args.no_judge:
        print("\n" + "=" * 78)
        print("LLM-СУДЬЯ (оценка по смыслу: покрытие эталона + качество + вердикт)")
        print("=" * 78)
        raw = ""
        try:
            j, raw = llm_judge(golden, pred_full(args.pred), llm)
        except Exception as e:  # noqa: BLE001
            print(f"судья недоступен: {e}"); j = None
        if isinstance(j, dict):
            cov = j.get("coverage", [])
            cc = {"covered": 0, "partial": 0, "missed": 0}
            for c in cov:
                st = c.get("status", "missed"); cc[st] = cc.get(st, 0) + 1
                mark = {"covered": "✓", "partial": "≈", "missed": "·"}.get(st, "·")
                mb = c.get("matched_by", -1)
                print(f"  {mark} [{st:<8}] {str(c.get('golden',''))[:46]}"
                      + (f"  ← наша #{mb}" if isinstance(mb, int) and mb >= 0 else ""))
            q = j.get("quality", {})
            print(f"\n  качество: specificity={q.get('specificity','?')} "
                  f"testability={q.get('testability','?')} "
                  f"relevance={q.get('relevance','?')} grounding={q.get('grounding','?')}")
            extra = j.get("extra_useful", [])
            print(f"  покрытие эталона (судья): covered={cc.get('covered',0)} "
                  f"partial={cc.get('partial',0)} missed={cc.get('missed',0)} "
                  f"| полезных сверх эталона: {len(extra)}")
            print(f"\n  ВЕРДИКТ: наши гипотезы — {str(j.get('verdict','?')).upper()} эталона")
            print(f"  {j.get('reasoning','')}")
        else:
            print("судья не вернул валидный JSON. Сырой ответ (первые 600 симв.):")
            print("  " + (raw[:600].replace("\n", "\n  ") if raw else "<пусто>"))


if __name__ == "__main__":
    main()
