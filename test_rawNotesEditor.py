from unittest import TestCase

import requests
from bs4 import BeautifulSoup

from RawNotesEditor import RawNotesEditor


class TestrawNotesEditor(TestCase):
    def setUp(self):
        self.raw_notes_editor = RawNotesEditor()
        
    def test_dicky_similar_phrases(self):
        word = "eyepatch"
        url = "https://www.diki.pl/slownik-angielskiego?q=" + word
        response = requests.get(url)
        html = response.text
        
        soup = BeautifulSoup(html, "html.parser")
        
        elements = self.raw_notes_editor.dicky_similar_phrases(soup)
        print(elements)

    def test_dicky_possible_spellings(self):
        word = "eyepatch"
        url = "https://www.diki.pl/slownik-angielskiego?q=" + word
        response = requests.get(url)
        html = response.text
        
        soup = BeautifulSoup(html, "html.parser")
        elements = self.raw_notes_editor.dicky_possible_spellings(soup)
        
        print(elements)