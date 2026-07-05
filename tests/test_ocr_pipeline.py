from __future__ import annotations

import os
import tempfile
import unittest

_FAKE_OCR_TEXT = """Сода 250–300 г/т
Руда 52–56 % класса -0,074 мм
Бутиловый ксантогенат 40–50 г/т
Измельчение и классификация в гидроциклонах
Основная коллективная флотация pH 8,5–9,5
Перечистная флотация концентрата
Контрольная флотация хвостов
Сгущение и фильтрация концентрата
Хвосты в отвал после контрольной флотации
Медный купорос 10–15 г/т для активации сфалерита
Известь до pH 10 для депрессии пирита
Отсадка крупного класса перед измельчением"""

class _FakeOCR:
    ready = True

    def recognize(self, data, mime="image/png", timeout=60):
        return _FAKE_OCR_TEXT

    def probe(self):
        return True

class TestOcrPipeline(unittest.TestCase):
    def test_image_chunk_passes_extraction_filters(self):
        from factory.trackb.extract import MIN_PROSE_CHARS, _select
        from factory.trackb.ingest import ingest, split

        with tempfile.TemporaryDirectory() as td:
            img = os.path.join(td, "data", "схемы", "Схема флотации.png")
            os.makedirs(os.path.dirname(img))
            open(img, "wb").write(b"\x89PNG\r\n\x1a\nfake")

            chunks = split(ingest([img], ocr=_FakeOCR()))
            self.assertEqual(len(chunks), 1)
            c = chunks[0]

            self.assertTrue(c.meta.get("ocr"))
            self.assertEqual(c.role, "state")

            self.assertGreaterEqual(len(c.text), MIN_PROSE_CHARS)
            alpha = sum(ch.isalpha() for ch in c.text) / len(c.text)
            self.assertGreaterEqual(alpha, 0.55)
            sel = _select(chunks, 5, "снизить потери никеля флотация")
            self.assertEqual(len(sel), 1, "OCR-чанк схемы обязан проходить отбор")

    def test_empty_ocr_marks_needs_ocr(self):
        from factory.trackb.ingest import ingest

        class _MuteOCR(_FakeOCR):
            def recognize(self, *a, **k):
                return ""

        with tempfile.TemporaryDirectory() as td:
            img = os.path.join(td, "скан.png")
            open(img, "wb").write(b"\x89PNG\r\n\x1a\nfake")
            chunks = ingest([img], ocr=_MuteOCR())
            self.assertEqual(len(chunks), 1)
            self.assertTrue(chunks[0].meta.get("needs_ocr"),
                            "пустое распознавание должно честно помечаться")

if __name__ == "__main__":
    unittest.main()
