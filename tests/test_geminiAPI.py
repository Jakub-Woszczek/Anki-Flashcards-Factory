from unittest import TestCase
from external_APIs.geminiAPI import GeminiBot


class TestGeminBot(TestCase):

    def test_get_word_translation(self):

        bot = GeminiBot()
        test_cases = ["ruffled"]

        for test_case in test_cases:
            print(bot.get_word_translation(test_case))
