from unittest import TestCase
from dikiApi import DikiApi


class TestDikiApi(TestCase):
    def setUp(self):
        self.DikiApi = DikiApi()

    def test_diki_possible_spellings(self):
        test_cases = [
            "stanch",
            "faculty",
            "broad walk",
            "eyepatch",
            "tossed up",
            "naiads",
            "tranquilizer dart",
            "pat",
        ]
        for phrase in test_cases:
            print(f"Testing {phrase}")
            result = self.DikiApi.dicky_possible_spellings(phrase)
            print(result)

    def test_diki_audio_harness(self):
        test_cases = ["eddying", "Be my guest.", "scooping", "overflow"]
        for phrase in test_cases:
            print(f"Testing {phrase}")
            result = self.DikiApi.diki_audio_harness(phrase, f"tmp")
            print(result)
