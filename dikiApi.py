import os
import re

import requests
from bs4 import BeautifulSoup


class DikiApi:
    def __init__(self):
        self.audio_path = (
            r"C:\Users\icefr\AppData\Roaming\Anki2\Użytkownik 1\collection.media"
        )
        pass

    def dicky_possible_spellings(self, phrase):
        """Returns list of possible spellings or phrasal verbs"""
        phrase = prepare_phrase_to_url(phrase)
        url = "https://www.diki.pl/slownik-angielskiego?q=" + phrase
        response = requests.get(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        # Znajdź wszystkie elementy słownika
        dictionary_entities = soup.select("div.dictionaryEntity")

        phrases = self.diki_similar_phrases(soup)
        for entity in dictionary_entities:
            # Znajdź wszystkie <div class="hws"> -> <span class="hw">
            hw_spans = entity.select("div.hws span.hw:not(.hwLessPopularAlternative)")
            for hw_span in hw_spans:
                text = hw_span.get_text()
                text = text.replace("\xa0", " ")
                text = " ".join(text.split())
                phrases.append(text)

        return phrases

    def word_request_diki(self, word):
        """If word is misspelled returns True"""
        # TODO Take code from Diki package, and put it here, and polish it with edge cases
        url = "https://www.diki.pl/slownik-angielskiego?q=" + word
        response = requests.get(url)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        spellings = self.dicky_possible_spellings(soup)
        for spelling in spellings:
            if word == spelling:
                return spellings

        return "Nie znaleziono dokładnego tłumaczenia" in soup.get_text()

    def diki_similar_phrases(self, soup):
        suggestions_div = soup.find("div", class_="dictionarySuggestions")
        suggestions = []

        if suggestions_div:
            # Szukamy wszystkich linków <a> w tym divie
            links = suggestions_div.find_all("a")
            for link in links:
                suggestions.append(link.get_text())

        return suggestions

    def diki_audio_harness(self, phrase, audio_path=None):
        word = phrase.replace(" ", "_")
        word = re.sub(r"[^\w_-]", "", word).lower()

        safe_phrase = re.sub(r'[<>:"/\\|?*]', "", phrase)

        url_british = f"https://www.diki.pl/images-common/en/mp3/{word}.mp3"
        url_american = f"https://www.diki.pl/images-common/en-ame/mp3/{word}.mp3"

        target_dir = self.audio_path if audio_path is None else audio_path
        filename = os.path.join(target_dir, f"{safe_phrase}.mp3")

        r_british = requests.get(url_british)
        if r_british.ok:
            with open(filename, "wb") as f:
                f.write(r_british.content)
            return True

        r_american = requests.get(url_american)
        if r_american.ok:
            with open(filename, "wb") as f:
                f.write(r_american.content)
            return True
        return False


def prepare_phrase_to_url(phase):
    phase = phase.strip().lower()
    words = phase.split(" ")
    return "+".join(words)
