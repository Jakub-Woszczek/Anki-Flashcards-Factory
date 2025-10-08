from unittest import TestCase

from flashcardApp import FlashcardApp, FlashcardAppConsole


class TestFlashcardApp(TestCase):

    def test_overall(self):
        path = r"other/flashcard_app_test_words.txt"
        test_deck = "English::toSort"
        self.app = FlashcardApp(path, test_deck)

    def test__on_def_and_vis_request(self):
        console = FlashcardAppConsole()
        with open(r"other/flashcard_app_test_words.txt", "r") as f:
            for word in f:
                print(word)
                console.on_def_and_vis_request(word)
