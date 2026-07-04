# -*- coding: utf-8 -*-
"""Предобработка картинки ПЕРЕД OCR (только Pillow, без numpy).

Схемы флотации и регламенты — сканы ужасного качества; чистка ощутимо поднимает
распознаваемость Yandex Vision. Безопасный набор (по умолчанию):
  1. grayscale — убрать цветовой шум;
  2. автоконтраст — растянуть гистограмму (выцветшие сканы);
  3. апскейл мелкого текста (LANCZOS) — OCR лучше читает крупные глифы;
  4. лёгкая резкость (unsharp) — подчеркнуть контуры букв/подписей.
Бинаризация (глобальный порог) — опция OFF по умолчанию: на неравномерном освещении
скана она чаще ВРЕДИТ (съедает светлый текст), поэтому включается осознанно.

Всё мягко деградирует: нет Pillow / битый файл → возвращаем исходные байты (OCR
попробует как есть). Функция чистая и детерминированная.
"""
from __future__ import annotations

import io

from factory.config import OCR_BINARIZE, OCR_PREPROCESS, OCR_UPSCALE_MIN_PX

# сигнатура применённых шагов — для инвалидации OCR-кэша при смене политики
def preprocess_tag() -> str:
    return f"pp{int(OCR_PREPROCESS)}u{OCR_UPSCALE_MIN_PX}b{int(OCR_BINARIZE)}"


def preprocess(data: bytes) -> bytes:
    """bytes картинки → очищенные bytes PNG. При любой проблеме — исходные bytes."""
    if not OCR_PREPROCESS:
        return data
    try:
        from PIL import Image, ImageFilter, ImageOps
    except Exception:  # noqa: BLE001  (нет Pillow — отдаём как есть)
        return data
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        im = ImageOps.exif_transpose(im)          # учесть поворот из EXIF
        im = im.convert("L")                       # grayscale
        im = ImageOps.autocontrast(im, cutoff=1)   # растянуть контраст, отсечь 1% выбросов
        # апскейл, если мелко: крупный текст распознаётся заметно лучше
        short = min(im.size)
        if short and short < OCR_UPSCALE_MIN_PX:
            k = min(3.0, OCR_UPSCALE_MIN_PX / short)
            im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        im = im.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))
        if OCR_BINARIZE:
            im = im.point(lambda p: 255 if p > 160 else 0, mode="L")
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return data
