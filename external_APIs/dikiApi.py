import os
import re

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


class DikiApi:
    def __init__(self):
        self.audio_path = os.getenv("ANKI_MEDIA_FOLDER_PATH")

    def possible_spellings(self, phrase) -> set:
        """
        Jeżeli diki poprawnie rozpozna fraze, może ona mieć parę synonimów/innych zapisów, np. jak słowo eyepatch,
        funkcja ta zbiera wszystkie podane przez diki synonimy/inne zapisy frazy.

        WARNING: Nie działa dla słów o takim samym zapisie po angielsku i po polsku (tbh nie jest ich dużo)
        """
        phrase = prepare_phrase_to_url(phrase)
        url = "https://www.diki.pl/slownik-angielskiego?q=" + phrase
        response = requests.get(url, headers=HEADERS)
        html = response.text

        soup = BeautifulSoup(html, "html.parser")

        # Znajdź wszystkie elementy słownika
        dictionary_entities = soup.select("div.dictionaryEntity")

        phrases = self.similar_phrases(soup)
        for entity in dictionary_entities:
            # Znajdź wszystkie <div class="hws"> -> <span class="hw">
            hw_spans = entity.select("div.hws span.hw:not(.hwLessPopularAlternative)")
            for hw_span in hw_spans:
                text = hw_span.get_text()
                text = text.replace("\xa0", " ")
                text = " ".join(text.split())
                phrases.add(text)

        return phrases

    def similar_phrases(self, soup):
        """
        Zwraca listę słówek podpowiedzi diki, gdzie słówko nie występuje w diki, lecz są podobne np.
        'versality' -> [versatility, verticality]
        """
        suggestions_div = soup.find("div", class_="dictionarySuggestions")
        suggestions = set()

        if suggestions_div:
            # Szukamy wszystkich linków <a> w tym divie
            links = suggestions_div.find_all("a")
            for link in links:
                suggestions.add((link.get_text()))

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

                assert isinstance(target_dir, str)
                os.makedirs(target_dir, exist_ok=True)
                filename = os.path.join(target_dir, f"{safe_phrase}.mp3")

                url = (
                    f"https://www.diki.pl/images-common/{lang}/mp3/{word}{version}.mp3"
                )
                r = requests.get(url, headers=HEADERS)
                if r.ok:
                    with open(filename, "wb") as f:
                        f.write(r.content)
                    return True

        return False

    def get_translations(self, phrase):
        """
        Wykonuje hierarchiczną ekstrakcję tłumaczeń z serwisu Diki.pl.

        Proces przetwarzania struktury DOM:
        1. Filtrowanie encji (dictionaryEntity): Identyfikuje główne bloki
           znaczeniowe, grupujące definicje według części mowy lub kontekstu.
        2. Weryfikacja nagłówków (hws): Sprawdza zgodność haseł głównych
           (headwords) z szukaną frazą, co zapobiega pobieraniu przypadkowych
           sugestii lub słów podobnych.
        3. Ekstrakcja list znaczeń (ol): Lokalizuje wszystkie struktury listowe
           'foreignToNativeMeanings' wewnątrz zweryfikowanej encji, scalając
           rozproszone bloki tłumaczeń.
        4. Grupowanie rzędów synonimów (li): Traktuje każdy element listy 'li'
           jako odrębny zbiór bliskich synonimów.
        5. Selekcja słów (hw): Wyodrębnia konkretne tłumaczenia oznaczone
           klasą 'hw', zachowując strukturę listy list, co zapobiega
           mieszaniu się odmiennych znaczeń słowa.

        Struktura HTML:
        Strona (BeautifulSoup)
        └── dictionaryEntity (Blok słownikowy)
            ├── hws (Nagłówek - tu sprawdzasz dopasowanie słowa)
            └── ol (foreignToNativeMeanings - lista znaczeń)
                ├── li (Punkt 1: rząd synonimów)
                │   └── span.hw (Pojedyncze słowo polskie)
                └── li (Punkt 2: kolejny rząd synonimów)
                    └── span.hw (Pojedyncze słowo polskie)

        Args:
            phrase (str): Szukana fraza w języku angielskim lub polskim.

        Returns:
            list[list[str]]: Zagnieżdżona lista tłumaczeń, gdzie każda podlista
            reprezentuje odrębny kontekst znaczeniowy (synonimy).
        """

        result = requests.get(f"https://www.diki.pl/slownik-angielskiego?q={phrase}", headers=HEADERS)
        soup = BeautifulSoup(result.text, "html.parser")

        entities = soup.find_all("div", class_="dictionaryEntity")
        all_meanings = []

        for entity in entities:

            header_section = entity.find("div", class_="hws")
            if not header_section:
                continue

            # Słowa kluczowe z nagłówka (może być ich kilka np. dla staunch i stanch)
            header_words = [
                hw.get_text(strip=True).strip().lower()
                for hw in header_section.find_all("span", class_="hw")
            ]

            if phrase not in header_words:
                continue

            meanings_list = entity.find_all(
                "ol", class_="foreignToNativeMeanings"
            )  # Szukam wszystkich znaczeń
            for m_list in meanings_list:
                for li in m_list.find_all("li", recursive=False):

                    current_row_meanings = [
                        span.get_text(strip=True)
                        for span in li.find_all("span", class_="hw", recursive=False)
                    ]

                    if current_row_meanings:
                        all_meanings.append(current_row_meanings)

        return all_meanings


def prepare_phrase_to_url(phase):
    phase = phase.strip().lower()
    words = phase.split(" ")
    return "+".join(words)
