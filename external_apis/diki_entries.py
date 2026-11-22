"""Select genuine dictionary entries without losing the dictionary's spelling."""

from dataclasses import dataclass, field
from typing import TypedDict

from bs4 import BeautifulSoup, Tag

from external_apis.diki_page import english_entries


def spelling(text: str) -> str:
    return " ".join(text.split())


@dataclass
class EntrySelection:
    word: str | None
    entries: list[Tag]
    suggestions: list[str]
    case_sensitive: bool = False
    matching_headwords: list["MatchingHeadword"] = field(default_factory=list)


class MatchingHeadword(TypedDict):
    word: str
    caseSensitive: bool


def select_entries(
    soup: BeautifulSoup, phrase: str, *, allow_unique: bool = False, inflections: bool = False
) -> EntrySelection:
    phrase = spelling(phrase)
    candidates = []
    for entity in english_entries(soup) if allow_unique else soup.select("div.dictionaryEntity"):
        if (
            entity.select_one(":scope > ol.nativeToForeignEntrySlices") is not None
            and entity.select_one(":scope > ol.foreignToNativeMeanings") is None
        ):
            continue
        header = entity.find("div", class_="hws")
        if header is None:
            continue
        if allow_unique and entity.find("ol", class_="foreignToNativeMeanings") is None:
            continue
        selector = "span.hw, span.foreignTermText" if inflections else "span.hw"
        words = list(
            dict.fromkeys(spelling(hw.get_text(" ", strip=True)) for hw in header.select(selector))
        )
        if words:
            candidates.append((entity, words))

    suggestions = sorted(
        {word for _, words in candidates for word in words}
        | {spelling(a.get_text(" ", strip=True)) for a in soup.select(".dictionarySuggestions a")}
    )
    folded = {word for _, words in candidates for word in words if word.lower() == phrase.lower()}
    word = phrase if phrase in folded else next(iter(folded)) if len(folded) == 1 else None
    if word is None and not folded and allow_unique and len(candidates) == 1:
        word = candidates[0][1][0]
    if word is None:
        return EntrySelection(None, [], suggestions)
    variants = {
        value for _, words in candidates for value in words if value.lower() == word.lower()
    }
    selected = [(entity, words) for entity, words in candidates if word in words]
    alternatives = list(dict.fromkeys(value for _, words in selected for value in words))
    matching_headwords: list[MatchingHeadword] = [
        {
            "word": alternative,
            "caseSensitive": len(
                {
                    value
                    for _, words in candidates
                    for value in words
                    if value.lower() == alternative.lower()
                }
            )
            > 1,
        }
        for alternative in alternatives
    ]
    return EntrySelection(
        word, [entity for entity, _ in selected], [], len(variants) > 1, matching_headwords
    )
