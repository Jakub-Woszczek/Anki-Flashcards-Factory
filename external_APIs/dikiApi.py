import os
import re

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
REQUEST_TIMEOUT_SECONDS = 15


class DikiApi:
    def __init__(self):
        self.audio_path = os.getenv("ANKI_MEDIA_FOLDER_PATH")
        self.last_error = None
        self.last_audio_path = None

    def possible_spellings(self, phrase) -> set:
        """
        Jeżeli diki poprawnie rozpozna fraze, może ona mieć parę synonimów/innych zapisów, np. jak słowo eyepatch,
        funkcja ta zbiera wszystkie podane przez diki synonimy/inne zapisy frazy.

        WARNING: Nie działa dla słów o takim samym zapisie po angielsku i po polsku (tbh nie jest ich dużo)
        """
        phrase = prepare_phrase_to_url(phrase)
        url = "https://www.diki.pl/slownik-angielskiego?q=" + phrase
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            # Diki serves its "Czy chodziło ci o" suggestions on a 404 page.
            # The response still contains valid dictionarySuggestions markup.
            if response.status_code != 404:
                response.raise_for_status()
        except requests.RequestException:
            return set()

        soup = BeautifulSoup(response.text, "html.parser")

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
        self.last_error = None
        self.last_audio_path = None
        word = phrase.replace(" ", "_")
        word = re.sub(
            r"[^\w_-]", "", word
        ).lower()  # Deletes all that is not "a-zA-Z0-9_" and -

        # Deletes illegal file symbols (Win,Mac,Linux)
        illegal_chars = r'[<>:"/\\|?*\0:]'
        safe_phrase = re.sub(illegal_chars, "", phrase)

        langs = ["en", "en-ame"]
        versions = [
            "",
            "-v",
            "-n",
        ]  # Refers to the version of word like noun of verb (sometimes occurs)

        for lang in langs:
            for version in versions:

                target_dir = self.audio_path
                if audio_path is not None:
                    target_dir = os.path.join(os.path.dirname(__file__), audio_path)

                if not isinstance(target_dir, str) or not target_dir:
                    self.last_error = "ANKI_MEDIA_FOLDER_PATH is not configured"
                    return False
                try:
                    os.makedirs(target_dir, exist_ok=True)
                except OSError as error:
                    self.last_error = f"Anki media folder is unavailable: {error}"
                    return False
                filename = os.path.join(target_dir, f"{safe_phrase}.mp3")

                url = (
                    f"https://www.diki.pl/images-common/{lang}/mp3/{word}{version}.mp3"
                )
                try:
                    r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
                except requests.RequestException:
                    continue
                if r.ok:
                    try:
                        with open(filename, "wb") as f:
                            f.write(r.content)
                    except OSError as error:
                        self.last_error = f"Could not write Diki audio: {error}"
                        return False
                    self.last_audio_path = filename
                    return True

        self.last_error = f"Diki has no downloadable audio for {phrase}"
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

        try:
            result = requests.get(
                f"https://www.diki.pl/slownik-angielskiego?q={prepare_phrase_to_url(phrase)}",
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            result.raise_for_status()
        except requests.RequestException:
            return []

        return parse_translations(result.text, phrase)


def parse_translations(html: str, phrase: str) -> list[list[str]]:
    """Parse a saved or fetched Diki document without performing I/O."""
    normalized_phrase = " ".join(phrase.lower().split())
    soup = BeautifulSoup(html, "html.parser")

    entities = soup.find_all("div", class_="dictionaryEntity")
    all_meanings = []

    for entity in entities:

        header_section = entity.find("div", class_="hws")
        if not header_section:
            continue

        # Słowa kluczowe z nagłówka (może być ich kilka np. dla staunch i stanch)
        # Uwaga: niektóre hasła zawierają zagnieżdżone <span class="stopword">
        # (np. "whatever floats <span class="stopword">one's</span> boat"),
        # więc trzeba wymusić separator, inaczej słowa się sklejają
        # (np. "whatever floatsone'sboat").
        header_words = [
            " ".join(hw.get_text(separator=" ", strip=True).split()).lower()
            for hw in header_section.find_all("span", class_="hw")
        ]

        if normalized_phrase not in header_words:
            continue

        meanings_list = entity.find_all(
            "ol", class_="foreignToNativeMeanings"
        )  # Szukam wszystkich znaczeń
        for m_list in meanings_list:
            for li in m_list.find_all("li", recursive=False):

                current_row_meanings = []
                for child in li.find_all("span", recursive=False):
                    classes = child.get("class", [])
                    if "hw" in classes:
                        spans = [child]
                    elif "hiddenNotForChildrenMeaning" in classes:
                        spans = child.find_all("span", class_="hw", recursive=False)
                    else:
                        spans = []
                    current_row_meanings.extend(
                        " ".join(span.get_text(separator=" ", strip=True).split())
                        for span in spans
                    )

                if current_row_meanings:
                    all_meanings.append(current_row_meanings)

    return all_meanings


def prepare_phrase_to_url(phase):
    phase = phase.strip().lower()
    words = phase.split(" ")
    return "+".join(words)
