from unittest import TestCase
from external_APIs.dikiApi import DikiApi


class TestDikiApi(TestCase):
    def setUp(self):
        self.DikiApi = DikiApi()

    def test_diki_possible_spellings(self):
        test_cases = [
            "stanch",
            "faculty",
            "broad walk",
            "eyepatch",
            "toss up",
            "naiads",
            "tranquilizer dart",
            "pat",
            "versality",
            "take",
            "taxi",
        ]
        for phrase in test_cases:
            print(f"Testing {phrase}")
            result = self.DikiApi.possible_spellings(phrase)
            print(result)

    def test_diki_audio_harness(self):
        test_cases = ["eddying", "Be my guest.", "scooping", "overflow"]
        for phrase in test_cases:
            print(f"Testing {phrase}")
            result = self.DikiApi.diki_audio_harness(phrase, f"tmp")
            print(result)

    def test_get_translations(self):
        test_cases = [
            "stanch",
            "faculty",
            "broad walk",
            "eyepatch",
            "toss up",
            "naiad",
            "tranquilizer dart",
            "pat",
        ]

        for phrase in test_cases:
            print(f"Testing {phrase}")
            print(self.DikiApi.get_translations(phrase))
