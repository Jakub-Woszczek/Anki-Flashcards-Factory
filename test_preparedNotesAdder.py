import os
from unittest import TestCase

import requests

from preparedNotesAdder import FlashcardApp
from preparedNotesAdder import parse_translations_to_html

class TestPreparedNotesAdder(TestCase):
    
    def test_diki_audio_harness(self):
        word = "thank you"
        autio_path = r"db"
        prepared_word = "".join(letter if letter != " " else "_" for letter in word)
        url = f"https://www.diki.pl/images-common/en/mp3/{prepared_word}.mp3"
        
        filename = os.path.join(autio_path, f"{prepared_word}.mp3")
        r = requests.get(url)
        with open(filename, "wb") as f:
            f.write(r.content)
    