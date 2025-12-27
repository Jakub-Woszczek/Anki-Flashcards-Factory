import os
import re

import requests
from bs4 import BeautifulSoup


class DikiApi:
    def __init__(self):
        self.audio_path = os.getenv("ANKI_MEDIA_FOLDER_PATH")
        pass

    def dicky_possible_spellings(self, phrase):
        """
        Jeżeli diki poprawnie rozpozna fraze, może ona mieć parę synonimów/innych zapisów, np. jak słowo eyepatch,
        funkcja ta zbiera wszystkie podane przez diki synonimy/inne zapisy frazy.
        """
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
        """
        Metoda pobiera dźwięk danego słowa ze słownika Diki, zapisuje go do folderu z mediami Anek
        lub do folderu w katalogu projektu, jeżeli @audio_path nie jest None.

        Sprawdza wersje url, czasami słowo występuje tylko w jednym wariancie językowym, en/ame oraz
        w wariancie dla formy słowa (rzeczownik/czasownik).
        """
        word = phrase.replace(" ", "_")
        word = re.sub(
            r"[^\w_-]", "", word
        ).lower()  # Deletes all that is not "a-zA-Z0-9_" and -

        # Deletes illegal file symbols (Win,Mac,Linux)
        illegal_chars = r'[<>:"/\\|?*\0:]'
        safe_phrase = re.sub(illegal_chars, "", phrase)

        langs = ["en", "en-ame"]
        version = [
            "",
            "-v",
            "-n",
        ]  # Refers to the version of word like noun of verb (sometimes occurs)

        for lang in langs:
            for version in version:

                target_dir = self.audio_path
                if audio_path is not None:
                    target_dir = os.path.join(os.path.dirname(__file__), audio_path)

                os.makedirs(target_dir, exist_ok=True)

                assert isinstance(target_dir, str)
                filename = os.path.join(target_dir, f"{safe_phrase}.mp3")

                url = (
                    f"https://www.diki.pl/images-common/{lang}/mp3/{word}{version}.mp3"
                )
                r = requests.get(url)
                if r.ok:
                    with open(filename, "wb") as f:
                        f.write(r.content)
                    return True

        return False


def prepare_phrase_to_url(phase):
    phase = phase.strip().lower()
    words = phase.split(" ")
    return "+".join(words)
