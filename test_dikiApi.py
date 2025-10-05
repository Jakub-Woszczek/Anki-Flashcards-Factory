from unittest import TestCase

from diki_translate import Diki

from dikiApi import DikiApi


class TestDikiApi(TestCase):
    def setUp(self):
        self.dikiApi = DikiApi()
        self.diki_package = Diki("english")

    def test_dicky_possible_spellings(self):
        test_cases = [
            "stanch",
            "faculty",
            "broad walk",
            "eyepatch",
            "tossed up",
            "naiads",
            "tranquilizer dart",
        ]
        phrase = "pat"
        result = self.dikiApi.dicky_possible_spellings(phrase)
        print(result)

    def test_diki_audio_harness(self):
        test_cases = ["eddying", "Be my guest.", "scooping"]
        result = self.dikiApi.diki_audio_harness("shoving", r"trash_can")
        print(result)

    def test_diki_translation(self):
        word = "trot"
        result = self.dikiApi.get_translations(word)
        print(result)
