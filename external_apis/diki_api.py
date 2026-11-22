from dataclasses import dataclass, field
from typing import TypedDict, cast

from bs4 import BeautifulSoup, Tag

from external_apis.diki_entries import MatchingHeadword, select_entries
from external_apis.diki_page import DikiPage, english_entries, headwords, inspect_page
from external_apis.diki_resources import DikiResources, ResourceError


class SentenceExample(TypedDict):
    english: str
    polish: str


class Meaning(TypedDict):
    translations: list[str]
    examples: list[SentenceExample]


@dataclass
class DikiLookup:
    word: str | None
    meanings: list[Meaning]
    suggestions: list[str]
    case_sensitive: bool = False
    page: DikiPage | None = None
    entry_choices: list[str] = field(default_factory=list)
    related_entries: list[str] = field(default_factory=list)
    matching_headwords: list[MatchingHeadword] = field(default_factory=list)

    @property
    def translations(self) -> list[list[str]]:
        return [meaning["translations"] for meaning in self.meanings]


def resolve_lookup(html: str, phrase: str) -> DikiLookup:
    soup = BeautifulSoup(html, "html.parser")
    page = inspect_page(soup)
    selection = select_entries(soup, phrase, allow_unique=True)
    return DikiLookup(
        selection.word,
        _entry_meanings(selection.entries),
        list(page.spelling_suggestions) if page.kind == "suggestions" else [],
        selection.case_sensitive,
        page,
        list(page.entry_choices) if selection.word is None and page.kind == "entries" else [],
        list(page.related_entries) if page.kind == "related" else [],
        selection.matching_headwords,
    )


class DikiApi:
    def __init__(self, resources=None):
        self.resources = resources if resources is not None else DikiResources()
        self.last_error = None

    def possible_spellings(self, phrase) -> set:
        """
        Jeżeli diki poprawnie rozpozna fraze, może ona mieć parę synonimów/innych zapisów, np. jak słowo eyepatch,
        funkcja ta zbiera wszystkie podane przez diki synonimy/inne zapisy frazy.

        WARNING: Nie działa dla słów o takim samym zapisie po angielsku i po polsku (tbh nie jest ich dużo)
        """
        self.last_error = None
        try:
            html = self.resources.fetch_html(phrase)
        except ResourceError as error:
            self.last_error = str(error)
            return set()

        return self._spellings_from_html(html)

    def _spellings_from_html(self, html) -> set:
        soup = BeautifulSoup(html, "html.parser")

        # Znajdź wszystkie elementy słownika
        dictionary_entities = english_entries(soup)

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

    def lookup(self, phrase, *, headword: str | None = None) -> DikiLookup:
        """One resource read, with per-call failures instead of shared error state."""
        html = self.resources.fetch_html(phrase)
        if headword is not None:
            available = {
                word
                for entry in english_entries(BeautifulSoup(html, "html.parser"))
                for word in headwords(entry)
            }
            if headword not in available:
                raise ResourceError("That headword is not an English→Polish entry in this response")
        result = resolve_lookup(html, headword if headword is not None else phrase)
        if headword is not None and result.word:
            self.resources.retain_headword(phrase, result.word, html)
        return result

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
                suggestions.add(link.get_text())

        return suggestions

    def fetch_audio(self, phrase) -> bytes:
        return self.resources.fetch_audio(phrase)

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

        return [meaning["translations"] for meaning in self.get_meanings(phrase)]

    def get_meanings(self, phrase: str) -> list[Meaning]:
        """Fetch exact-match meanings with their attached English/Polish examples.

        The separate, automatically generated additional-sentences section is
        excluded. Each example belongs to its containing meaning group.
        """
        self.last_error = None
        try:
            html = self.resources.fetch_html(phrase)
        except ResourceError as error:
            self.last_error = str(error)
            return []

        return parse_meanings(html, phrase)


def parse_translations(html: str, phrase: str) -> list[list[str]]:
    """Return translation groups only, preserving the app's existing contract."""
    return [meaning["translations"] for meaning in parse_meanings(html, phrase)]


def parse_meanings(html: str, phrase: str) -> list[Meaning]:
    """Parse meanings and attached bilingual examples without performing I/O."""
    soup = BeautifulSoup(html, "html.parser")
    return _entry_meanings(select_entries(soup, phrase).entries)


def _entry_meanings(entities: list[Tag]) -> list[Meaning]:
    all_meanings = []

    for entity in entities:
        meanings_list = entity.find_all(
            "ol", class_="foreignToNativeMeanings"
        )  # Szukam wszystkich znaczeń
        for m_list in meanings_list:
            for li in m_list.find_all("li", recursive=False):
                current_row_meanings = []
                for child in li.find_all("span", recursive=False):
                    classes = cast(list[str] | str, child.attrs.get("class", []))
                    if "hw" in classes:
                        spans = [child]
                    elif "hiddenNotForChildrenMeaning" in classes:
                        spans = child.find_all("span", class_="hw", recursive=False)
                    else:
                        spans = []
                    current_row_meanings.extend(
                        " ".join(span.get_text(separator=" ", strip=True).split()) for span in spans
                    )

                if current_row_meanings:
                    examples = []
                    for example in li.select(".exampleSentence"):
                        translation = example.find(class_="exampleSentenceTranslation")
                        polish = ""
                        if translation is not None:
                            polish = " ".join(translation.get_text(" ", strip=True).split())
                            if polish.startswith("(") and polish.endswith(")"):
                                polish = polish[1:-1].strip()

                        # Remove the translation and controls before reading the
                        # English sentence, preserving any inline sentence markup.
                        for extra in example.select(
                            ".exampleSentenceTranslation, .recordingsAndTranscriptions, "
                            ".repetitionAddOrRemoveIconAnchor"
                        ):
                            extra.decompose()
                        english = " ".join(example.get_text(" ", strip=True).split())
                        if english:
                            examples.append({"english": english, "polish": polish})
                    all_meanings.append(
                        {
                            "translations": current_row_meanings,
                            "examples": examples,
                        }
                    )

    return all_meanings
