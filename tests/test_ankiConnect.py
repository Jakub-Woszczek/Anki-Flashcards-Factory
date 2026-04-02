from unittest import TestCase
from dotenv import load_dotenv

from external_APIs.ankiConnect import AnkiConnect


class TestAnkiConnect(TestCase):
    def setUp(self):
        load_dotenv()
        self.anki = AnkiConnect()

    def test_add_flashcard(self):
        result = self.anki.add_flashcard(
            "enslih word", "pl t", "audio", "English::toSort", ["cos"]
        )
        print(result)

    def test_move_note_to_deck(self):
        note_id = 1755851157741
        self.anki.move_note_to_deck(note_id, "English::test2")

    def test_get_subdecks(self):
        r = self.anki.get_subdecks()
        print(r)

    def test_notes_ids_from_deck(self):
        r = self.anki.notes_ids_from_deck("English::1#")
        print(r)
