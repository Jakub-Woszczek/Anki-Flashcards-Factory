"""Pure recognition of Diki result content, independent of query resolution."""

from dataclasses import dataclass
from typing import Literal

from bs4 import BeautifulSoup, Tag

PageKind = Literal["entries", "suggestions", "related", "collocation", "not_found", "unknown"]
NEGATIVE_NOTICE = "Nie znaleziono dokładnego tłumaczenia wpisanej frazy."
WORD_BY_WORD_NOTICE = "Poniżej prezentujemy tłumaczenia poszczególnych wyrazów."


def text(node: Tag) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def headwords(entity: Tag) -> list[str]:
    return list(
        dict.fromkeys(text(hw) for hw in entity.select(":scope > .hws span.hw") if text(hw))
    )


def english_entries(soup: BeautifulSoup | Tag) -> list[Tag]:
    scope = soup.select_one("#contentWrapper > .dikiContainer") or soup
    return [
        entity
        for entity in scope.select("div.dictionaryEntity")
        if headwords(entity)
        and any(
            text(span)
            for span in entity.select(
                ":scope > ol.foreignToNativeMeanings > li > span.hw, "
                ":scope > ol.foreignToNativeMeanings > li > "
                "span.hiddenNotForChildrenMeaning > span.hw"
            )
        )
    ]


def _reverse_section(entity: Tag, scope: Tag) -> bool:
    """Read section headings, not the page title or related-link labels."""
    block: Tag = entity
    while isinstance(block.parent, Tag) and block.parent is not scope:
        block = block.parent
    for sibling in block.previous_siblings:
        if not isinstance(sibling, Tag):
            continue
        headers = (
            [sibling]
            if "dictionarySectionHeader" in (sibling.get("class") or ())
            else sibling.select(".dictionarySectionHeader")
        )
        for header in reversed(headers):
            # Exclude the 'zobacz ...' link to the other dictionary direction.
            label = text(header).split("|")[0]
            if "Słownik polsko-angielski" in label:
                return True
            if "Słownik angielsko-polski" in label:
                return False
    return False


@dataclass(frozen=True)
class DikiPage:
    kind: PageKind
    entry_choices: tuple[str, ...]
    spelling_suggestions: tuple[str, ...]
    related_entries: tuple[str, ...]
    has_reverse_entries: bool
    has_collocations: bool
    no_exact_translation: bool
    word_by_word: bool

    @property
    def recognized(self) -> bool:
        return self.kind != "unknown"


def inspect_page(soup: BeautifulSoup) -> DikiPage:
    # Reduced regression fixtures need not contain the surrounding website shell.
    scope = soup.select_one("#contentWrapper > .dikiContainer") or soup
    entries = english_entries(scope)
    choices = tuple(dict.fromkeys(headwords(entry)[0] for entry in entries))
    suggestions = tuple(
        dict.fromkeys(text(link) for link in scope.select(".dictionarySuggestions a") if text(link))
    )
    related = []
    for row in scope.select(".dictionaryEntity > .fentry"):
        if row.find_parent(class_="wordByWordTranslation") is not None or _reverse_section(
            row, scope
        ):
            continue
        first = row.select_one(".fentrymain .hw")
        if first is not None and text(first):
            related.append(text(first))
    reverse = any(
        headwords(entity) and entity.select_one(":scope > ol.nativeToForeignEntrySlices > li")
        for entity in scope.select(".dictionaryEntity")
    )
    collocations = False
    for unit in scope.select(".collocationSearchResults .dictionaryCollocationUnits"):
        heading = unit.select_one(":scope > .hws .hw")
        if (
            heading is not None
            and text(heading)
            and unit.select_one(":scope > ol.foreignToNativeMeanings > li .collocationUnitHeader")
            is not None
        ):
            collocations = True
    notices = [text(p) for p in scope.find_all("p", recursive=False)]
    negative = bool(scope.select_one(".dictionaryNoResults")) or any(
        NEGATIVE_NOTICE.casefold() in notice.casefold()
        or notice.casefold() in {"nie znaleziono", "brak wyników"}
        for notice in notices
    )
    word_by_word = bool(scope.select_one(".wordByWordTranslation")) or any(
        WORD_BY_WORD_NOTICE.casefold() in notice.casefold() for notice in notices
    )
    kind: PageKind
    if entries:
        kind = "entries"
    elif suggestions:
        kind = "suggestions"
    elif collocations:
        kind = "collocation"
    elif related:
        kind = "related"
    elif negative or word_by_word or reverse:
        kind = "not_found"
    else:
        kind = "unknown"
    return DikiPage(
        kind,
        choices,
        suggestions,
        tuple(dict.fromkeys(related)),
        bool(reverse),
        collocations,
        negative,
        word_by_word,
    )
