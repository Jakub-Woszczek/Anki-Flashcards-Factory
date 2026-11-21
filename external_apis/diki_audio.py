"""Discover advertised headword recordings without guessing filenames or doing I/O."""

import re
from typing import cast
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from external_apis.diki_entries import select_entries

# Bump when selection rules change, so old negative results are reconsidered.
DISCOVERY_VERSION = 2


def _normalize(text):
    return " ".join(text.lower().replace("’", "'").split())


def _recording_url(value):
    try:
        url = urljoin("https://www.diki.pl/", value)
        parts = urlsplit(url)
    except ValueError:
        return None
    path = unquote(parts.path)
    # HTML is remote input: never turn an advertised URL into an arbitrary fetch.
    if (
        parts.scheme != "https"
        or parts.netloc != "www.diki.pl"
        or parts.query
        or parts.fragment
        or "\\" in path
        or any(ord(char) < 32 for char in url + path)
        or not re.fullmatch(r"/images-common/(en|en-ame)/mp3/[^/]+\.mp3", path)
        or path.rsplit("/", 1)[-1] in {"..mp3", ".mp3"}
    ):
        return None
    return url


def discover_audio_urls(html: str, word: str) -> list[str]:
    """Exact spelling first, then space-only variants in the same matching entry.

    A header can advertise several unrelated synonyms. Associate each recording
    with its preceding headword, rather than taking every audio icon in the entry.
    Hyphens are significant (e.g. resign/re-sign); sentence audio is never used.
    """
    phrase = _normalize(word)
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    selection = select_entries(soup, word, inflections=True)
    if not selection.entries:
        selection = select_entries(soup, word, allow_unique=True, inflections=True)
    phrase = _normalize(selection.word or word)
    for entity in selection.entries:
        header = entity.find("div", class_="hws")
        if header is None:
            continue
        headwords = header.select("span.hw, span.foreignTermText")
        if phrase not in {_normalize(hw.get_text(" ", strip=True)) for hw in headwords}:
            continue
        for hw in headwords:
            raw_spelling = " ".join(hw.get_text(" ", strip=True).split())
            spelling = _normalize(raw_spelling)
            if selection.case_sensitive and raw_spelling != selection.word:
                continue
            if spelling.replace(" ", "") != phrase.replace(" ", ""):
                continue
            for sibling in hw.next_siblings:
                if not isinstance(sibling, Tag):
                    continue
                if sibling.name == "br" or {"hw", "foreignTermText"}.intersection(
                    cast(list[str] | str, sibling.attrs.get("class", []))
                ):
                    break
                icons = [sibling] if sibling.has_attr("data-audio-url") else []
                icons += sibling.select("[data-audio-url]")
                for icon in icons:
                    url = _recording_url(icon["data-audio-url"])
                    if url:
                        candidates.append((spelling != phrase, "/en-ame/" in url, url))
    # Stable sort retains the advertised order within each spelling/dialect.
    candidates.sort(key=lambda item: item[:2])
    return list(dict.fromkeys(url for _, _, url in candidates))
