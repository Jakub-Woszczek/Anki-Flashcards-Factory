"""Select genuine dictionary entries without losing the dictionary's spelling."""

from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag


def spelling(text: str) -> str:
    return " ".join(text.split())


@dataclass
class EntrySelection:
    word: str | None
    entries: list[Tag]
    suggestions: list[str]
    case_sensitive: bool = False


def select_entries(
    soup: BeautifulSoup, phrase: str, *, allow_unique: bool = False, inflections: bool = False
) -> EntrySelection:
    phrase = spelling(phrase)
    candidates = []
    for entity in soup.select("div.dictionaryEntity"):
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
    return EntrySelection(
        word, [entity for entity, words in candidates if word in words], [], len(variants) > 1
    )
