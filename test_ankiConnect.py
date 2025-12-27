from unittest import TestCase

from ankiConnect import AnkiConnect


class TestAnkiConnect(TestCase):
    def setUp(self):
        self.anki = AnkiConnect()

    def test_add_flashcard(self):
        result = self.anki.add_flashcard(
            "enslih word", "pl t", "audio", "English::toSort", ["cos"]
        )
        print(result)

    def test_move_note_to_deck(self):
        note_id = 1755851157741
        self.anki.move_note_to_deck(note_id, "English::test2")
