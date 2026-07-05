from __future__ import annotations

_FAMILY_UNITS = {
    "раскрытие / измельчение": [
        "мельниц", "футеровк", "шар", "помол", "дробилк", "гал", "измельчител"],
    "извлечение шламов / классификация": [
        "гидроцикл", "циклон", "насадк", "классификатор", "грохот", "сгустит",
        "спиральн", "дешламатор"],
    "доизвлечение флотацией": [
        "флотац", "флотомашин", "камер", "чан", "аэрац", "пневм", "импеллер",
        "пенн", "колонн"],
    "реагентный режим / кинетика флотации": [
        "реагент", "собират", "депрессор", "ксантоген", "вспениват", "дозатор",
        "чан", "камер", "контактн"],
}

_MIN_UNIT = 4
_MAX_UNITS = 3

def _specificity(label: str) -> int:
    digits = sum(c.isdigit() for c in label)
    return digits * 3 + min(len(label), 60) // 10

def _candidate_units(relations: list) -> list:
    out, seen = [], set()
    for r in relations or []:
        quote = (r.get("quote") or "").strip()
        meta = r.get("meta") or {}
        src = r.get("source") or meta.get("file") or ""
        for role in ("subject", "object"):
            lbl = (r.get(role) or "").strip()
            key = lbl.lower()
            if len(lbl) < _MIN_UNIT or key in seen:
                continue

            if " " not in lbl and not any(c.isdigit() for c in lbl) and len(lbl) < 12:
                continue
            seen.add(key)
            out.append({"unit": lbl, "quote": quote, "locator": r.get("locator", "") or src,
                        "source": src, "page": meta.get("page")})
    return out

def bridge(hyps, relations: list, log=lambda *a: None) -> int:
    if not relations:
        return 0
    cands = _candidate_units(relations)
    if not cands:
        return 0
    n = 0
    for h in hyps:
        keys = _FAMILY_UNITS.get(getattr(h, "family", ""), [])
        if not keys:
            continue
        matched = [c for c in cands if any(k in c["unit"].lower() for k in keys)]
        if not matched:
            continue

        matched.sort(key=lambda c: (-_specificity(c["unit"]), c["unit"].lower()))
        h.bridge = matched[:_MAX_UNITS]
        n += 1
        log(f"  {h.size_class}/{h.family}: сшито с {len(h.bridge)} узлами схемы")
    return n
