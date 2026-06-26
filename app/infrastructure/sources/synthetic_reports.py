"""Синтетические отчёты о НИР + заряженные пары + рендер сканов.

- 16 отчётов, 9 из них — провалы с ЯВНОЙ причиной закрытия (closure_reason).
- 3 «заряженные пары»: провал с устаревшей причиной по РЕАЛЬНОМУ реагенту +
  свежая статья из корпуса (часть A), снимающая причину — топливо для генератора
  «реанимация». Пара строится только если в корпусе есть подходящая свежая статья.
- 5 отчётов дополнительно рендерятся в image-only PDF (Pillow) → честный вход для OCR.
Всё синтетическое: is_synthetic=True.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.service.entities import Document

KPI = "извлечение Ni, %"

_OUTCOME_RU = {
    "success": "успех — направление внедрено",
    "failure": "провал — направление закрыто",
    "neutral": "без значимого эффекта",
}


@dataclass
class Report:
    """Структурированный отчёт о НИР (исход/причина — для статистики и пар)."""

    id: str
    title: str
    year: int
    outcome: str  # success | failure | neutral
    attempt: str
    closure_reason: str | None = None
    reagent: str | None = None  # ключевая сущность (для заряженных пар)
    kpi: str = KPI

    def to_text(self) -> str:
        lines = [
            f"Отчёт о НИР {self.id}",
            f"Тема: {self.title}",
            f"Год: {self.year}",
            f"Целевой KPI: {self.kpi}",
            f"Описание попытки: {self.attempt}",
            f"Исход: {_OUTCOME_RU[self.outcome]}.",
        ]
        if self.outcome == "failure" and self.closure_reason:
            lines.append(f"Причина закрытия: {self.closure_reason}.")
        return "\n".join(lines)

    def to_document(self) -> Document:
        return Document(
            id=self.id,
            title=self.title,
            year=self.year,
            source="report",
            url=None,
            is_synthetic=True,
            is_scanned=False,
            text=self.to_text(),
            source_path=None,
        )


# --- базовые отчёты (6 провалов, 5 успехов, 2 нейтральных) --------------------

_BASE_REPORTS: list[Report] = [
    Report("rep_lime_ph", "Депрессия пирротина повышением pH известью", 2014, "failure",
           "Поднимали pH пульпы до 11.5 известью для подавления пирротина.",
           "при высоком pH росли потери никеля в хвостах — эффект на KPI отрицательный"),
    Report("rep_dextrin", "Декстрин как депрессор пустой породы", 2011, "failure",
           "Вводили декстрин для депрессии силикатной породы в основной флотации.",
           "результаты невоспроизводимы от партии к партии реагента"),
    Report("rep_column", "Колонная флотация вместо механической", 2015, "failure",
           "Пилотировали колонную флотацию для доизвлечения тонких классов.",
           "нет промышленного оборудования нужного масштаба на площадке"),
    Report("rep_xanthate", "Высокодозный бутиловый ксантогенат", 2013, "failure",
           "Повышали расход ксантогената для извлечения пентландита.",
           "рост извлечения меди в ущерб селективности по никелю"),
    Report("rep_heating", "Подогрев пульпы до 40°C", 2016, "failure",
           "Грели пульпу для ускорения кинетики флотации сульфидов никеля.",
           "экономически нецелесообразно: затраты на пар превышают эффект"),
    Report("rep_echem", "Электрохимическая модификация поверхности сульфидов", 2010, "failure",
           "Прикладывали потенциал для управления гидрофобностью пентландита.",
           "не соответствует нормативам реагентной и электробезопасности"),
    Report("rep_collector_dose", "Оптимизация расхода собирателя по зонам", 2017, "success",
           "Подбирали дозировку собирателя посекционно по результатам экспресс-анализа.",
           None),
    Report("rep_intercycle", "Двухстадиальная межцикловая флотация", 2018, "success",
           "Внедрили межцикловую флотацию для возврата богатых промпродуктов.", None),
    Report("rep_eh_control", "Контроль Eh пульпы азотной продувкой", 2019, "success",
           "Стабилизировали окислительно-восстановительный потенциал пульпы.", None),
    Report("rep_floc", "Селективная флокуляция тонких классов", 2012, "success",
           "Применяли селективный флокулянт для агрегации тонкого пентландита.", None),
    Report("rep_automation", "Автоматическое дозирование реагентов", 2020, "success",
           "Внедрили АСУ дозирования по онлайн-датчикам пенного слоя.", None),
    Report("rep_frother", "Замена пенообразователя МИБК на полигликоль", 2016, "neutral",
           "Сравнивали полигликолевый пенообразователь с МИБК.", None),
    Report("rep_magnetic", "Магнитная сепарация перед флотацией", 2018, "neutral",
           "Ставили магнитную сепарацию пирротина до флотационного передела.", None),
]


# --- заряженные пары (провал по реальному реагенту + свежая статья из корпуса) -


@dataclass
class ChargedSpec:
    """Спецификация заряженной пары: провал + ключевые слова для поиска свежего факта."""

    id: str
    title: str
    year: int
    attempt: str
    old_reason: str
    reagent: str
    keywords: list[str] = field(default_factory=list)


_CHARGED_SPECS: list[ChargedSpec] = [
    ChargedSpec(
        "rep_cmc",
        "Карбоксиметилцеллюлоза (CMC) как депрессор",
        2013,
        "Пробовали CMC для депрессии породообразующих минералов в Cu-Ni цикле.",
        "при тогдашних дозировках CMC снижала извлечение никеля — направление закрыли",
        "карбоксиметилцеллюлоза (CMC)",
        ["carboxymethyl cellulose", "carboxymethyl-cellulose", "cmc", "cellulose depressant"],
    ),
    ChargedSpec(
        "rep_dtp_collector",
        "Селективный собиратель класса дитиофосфинатов",
        2012,
        "Испытывали селективный дитиофосфинатный собиратель для пентландита.",
        "синтез селективного собирателя был слишком дорогим для промышленного применения",
        "дитиофосфинатный собиратель",
        ["dithiophosphinate", "dithiophosphate", "aerophine", "selective collector"],
    ),
    ChargedSpec(
        "rep_smbs",
        "Метабисульфит натрия (SMBS) для депрессии пирротина",
        2014,
        "Применяли SMBS для селективной депрессии пирротина относительно пентландита.",
        "депрессия пирротина метабисульфитом была нестабильной — от реагента отказались",
        "метабисульфит натрия (SMBS)",
        ["metabisulfite", "metabisulphite", "smbs", "pyrrhotite depression"],
    ),
]


def find_recent_match(corpus: list[Document], keywords: list[str], min_year: int = 2017) -> Document | None:
    """Самая свежая статья корпуса (year ≥ min_year), задевающая ключевые слова."""
    kws = [k.lower() for k in keywords]
    matches = [
        d
        for d in corpus
        if d.year >= min_year
        and any(k in f"{d.title} {d.text or ''}".lower() for k in kws)
    ]
    if not matches:
        return None
    return max(matches, key=lambda d: (d.year, d.id))


def build_reports(corpus: list[Document]) -> tuple[list[Report], list[dict]]:
    """Собрать отчёты (база + заряженные пары) и манифест найденных пар.

    Заряженная пара образуется, только если в корпусе нашлась свежая статья,
    снимающая причину — иначе отчёт остаётся обычным провалом без пары.
    """
    reports = list(_BASE_REPORTS)
    charged_pairs: list[dict] = []
    for spec in _CHARGED_SPECS:
        reports.append(
            Report(
                id=spec.id,
                title=spec.title,
                year=spec.year,
                outcome="failure",
                attempt=spec.attempt,
                closure_reason=spec.old_reason,
                reagent=spec.reagent,
            )
        )
        reviving = find_recent_match(corpus, spec.keywords)
        if reviving is not None:
            charged_pairs.append(
                {
                    "failure_report_id": spec.id,
                    "reagent": spec.reagent,
                    "old_reason": spec.old_reason,
                    "reviving_doc_id": reviving.id,
                    "reviving_title": reviving.title,
                    "reviving_year": reviving.year,
                    "reviving_url": reviving.url,
                }
            )
    return reports, charged_pairs


# --- рендер сканов (image-only PDF → честный вход для OCR) ---------------------

# какие отчёты сохранить ещё и сканом (вкл. 2 заряженные пары для OCR+реанимации)
SCAN_REPORT_IDS: list[str] = [
    "rep_cmc",
    "rep_smbs",
    "rep_xanthate",
    "rep_column",
    "rep_lime_ph",
]

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size: int):
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001 — пробуем следующий путь
            continue
    return ImageFont.load_default()


def _wrap(text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        cur = ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if font.getlength(trial) <= max_width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def render_scan_pdf(report: Report, out_path: Path) -> None:
    """Отрендерить отчёт как «скан»: текст → растровое изображение → PDF (без текстового слоя)."""
    from PIL import Image, ImageDraw

    W, H = 1240, 1754  # A4 @150dpi
    paper = (252, 251, 248)
    img = Image.new("RGB", (W, H), paper)
    draw = ImageDraw.Draw(img)
    margin = 96

    header_font = _load_font(22)
    title_font = _load_font(40)
    body_font = _load_font(30)

    draw.text((margin, 54), "АРХИВ НИОКР · СКАН ДОКУМЕНТА", font=header_font, fill=(120, 120, 120))
    draw.line([(margin, 92), (W - margin, 92)], fill=(180, 180, 180), width=2)

    y = 140
    for line in _wrap(report.title, title_font, W - 2 * margin):
        draw.text((margin, y), line, font=title_font, fill=(20, 20, 20))
        y += 52
    y += 18

    body = report.to_text().split("\n", 1)[1] if "\n" in report.to_text() else report.to_text()
    for line in _wrap(body, body_font, W - 2 * margin):
        draw.text((margin, y), line, font=body_font, fill=(35, 35, 35))
        y += 42

    # лёгкий «скан»-наклон, чтобы OCR работал по реальной картинке
    img = img.rotate(-0.7, expand=False, fillcolor=paper)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), "PDF", resolution=150.0)


def render_scans(reports: list[Report], scans_dir: Path, ids: list[str] | None = None) -> list[Document]:
    """Отрендерить выбранные отчёты в PDF-сканы; вернуть scan-версии Document.

    Scan-версия — отдельный Document того же отчёта: is_scanned=True, text=None,
    source_path указывает на PDF (вход для Ocr).
    """
    wanted = set(ids or SCAN_REPORT_IDS)
    by_id = {r.id: r for r in reports}
    scan_docs: list[Document] = []
    for rid in wanted:
        report = by_id.get(rid)
        if report is None:
            continue
        pdf_path = scans_dir / f"{rid}.pdf"
        render_scan_pdf(report, pdf_path)
        scan_docs.append(
            Document(
                id=f"{rid}__scan",
                title=report.title,
                year=report.year,
                source="report",
                url=None,
                is_synthetic=True,
                is_scanned=True,
                text=None,
                source_path=str(pdf_path),
            )
        )
    return scan_docs


__all__ = [
    "Report",
    "ChargedSpec",
    "build_reports",
    "find_recent_match",
    "render_scans",
    "render_scan_pdf",
    "SCAN_REPORT_IDS",
]
