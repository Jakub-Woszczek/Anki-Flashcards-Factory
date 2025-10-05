from http.client import responses
from lib2to3.fixes.fix_tuple_params import simplify_args
from unittest import TestCase
from geminiAPI import GeminBot


class TestGeminBot(TestCase):

    def test_get_word_translation(self):

        bot = GeminBot()
        test_cases = ["ruffled"]

        for test_case in test_cases:
            print(bot.get_word_translation(test_case))
