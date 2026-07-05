from __future__ import annotations

import io

from factory.config import OCR_BINARIZE, OCR_PREPROCESS, OCR_UPSCALE_MIN_PX


def preprocess_tag() -> str:
    return f"pp{int(OCR_PREPROCESS)}u{OCR_UPSCALE_MIN_PX}b{int(OCR_BINARIZE)}"

def preprocess(data: bytes) -> bytes:
    if not OCR_PREPROCESS:
        return data
    try:
        from PIL import Image, ImageFilter, ImageOps
    except Exception:
        return data
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        im = ImageOps.exif_transpose(im)
        im = im.convert("L")
        im = ImageOps.autocontrast(im, cutoff=1)

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
    except Exception:
        return data
