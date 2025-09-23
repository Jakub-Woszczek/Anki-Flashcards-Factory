from unittest import TestCase

from ankiConnect import AnkiConnect


class TestAnkiConnect(TestCase):
    def setUp(self):
        self.anki = AnkiConnect()

    def test_harness_cards_content(self):
        content = self.anki.harness_cards_content([1661626723874])
        front_note = self.anki.clean_html(content[0]["fields"]["Przód"]["value"])
        back_note = self.anki.clean_html(content[0]["fields"]["Tył"]["value"])
        
        print(front_note)
        print(back_note)
    
    def test_add_flashcard(self):
        result = self.anki.add_flashcard("enslih word","pl t","audio","English::toSort",["cos"])
        print(result)
        
    def test_move_note_to_deck(self):
        note_id = 1755851157741
        self.anki.move_note_to_deck(note_id,"English::test2")