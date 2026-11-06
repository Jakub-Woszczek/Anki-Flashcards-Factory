import json
from pathlib import Path
from unittest import TestCase

from bs4 import BeautifulSoup

from external_APIs.dikiApi import DikiApi, parse_translations


CASES_DIR = Path(__file__).parent / "diki_cases"


class TestDikiRegression(TestCase):
    def test_saved_edge_cases_match_their_expected_outcomes(self):
        cases = json.loads((CASES_DIR / "manifest.json").read_text(encoding="utf-8"))
        parser = DikiApi()

        for case in cases:
            with self.subTest(word=case["word"]):
                html = (CASES_DIR / case["fixture"]).read_text(encoding="utf-8")
                self.assertEqual(
                    parse_translations(html, case["word"]),
                    case["expectedTranslations"],
                )
                self.assertEqual(
                    sorted(parser.similar_phrases(BeautifulSoup(html, "html.parser"))),
                    case["expectedSuggestions"],
                )
