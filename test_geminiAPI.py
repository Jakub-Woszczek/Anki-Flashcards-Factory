from unittest import TestCase
from geminiAPI import GeminiBot


class TestGeminiBot(TestCase):

    def test_get_word_translation(self):

        bot = GeminiBot()
        test_cases = ["ruffled"]

        for test_case in test_cases:
            print(bot.get_word_translation(test_case))

    def test_get_word_sentences(self):

        bot = GeminiBot()
        test_cases = [
            ("computer", ["komputer", "maszyna licząca"]),
            ("book", []),
            ("travel", ["podróż", "podróżować", "wycieczka"]),
        ]

        for word, translations in test_cases:
            bot.get_word_sentences(word, translations)
