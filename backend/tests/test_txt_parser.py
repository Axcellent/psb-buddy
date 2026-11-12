import tempfile
import unittest
import zipfile
from pathlib import Path

from backend.app.services.txt_parser import parse_txt, parse_txt_zip


class TextParserTests(unittest.TestCase):
    def test_company_clauses_keep_exact_source_spans(self):
        text = (
            "ДОГОВОР № А-08/2024\n"
            "1. Предмет договора\n"
            "1.1. Первое условие.\nПродолжение условия.\n"
            "1.2. Второе условие.\n"
        )
        chunks = parse_txt("документы компании__договор.txt", text)
        self.assertEqual(
            [chunk.locator for chunk in chunks],
            [None, "разд. 1", "п. 1.1", "п. 1.2"],
        )
        self.assertIn("Продолжение условия", chunks[2].text)
        for chunk in chunks:
            self.assertEqual(chunk.text, text[chunk.start_char : chunk.end_char])

    def test_law_article_and_numbered_points(self):
        text = (
            "Источник: НК РФ\n\n"
            "Статья 164. Налоговые ставки\n"
            "1. Первый пункт.\n"
            "1) Первый подпункт.\n"
            "1.1) Следующий подпункт.\n"
        )
        chunks = parse_txt("законы__НК_ст164.txt", text)
        self.assertEqual(
            [chunk.locator for chunk in chunks],
            [
                None,
                "Статья 164",
                "Статья 164, п. 1",
                "Статья 164, подп. 1",
                "Статья 164, подп. 1.1",
            ],
        )

    def test_long_clause_is_bounded_and_zip_reads_utf8(self):
        text = "1.1. " + ("Условие повторяется. " * 80)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kb.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("документы компании__договор.txt", text)
            chunks = parse_txt_zip(path, max_chars=300, overlap_chars=30)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.text) <= 300 for chunk in chunks))
        self.assertTrue(all(chunk.locator == "п. 1.1" for chunk in chunks))
        self.assertTrue(all(chunk.text == text[chunk.start_char : chunk.end_char] for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
