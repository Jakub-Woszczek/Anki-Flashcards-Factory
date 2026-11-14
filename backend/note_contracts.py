"""Strict field parsers for the incremental rules in note-data-contracts.md."""

import re


CONTRACT_VERSION = 3
NOTE_TYPES = ("Basic [reverse+audio]", "Basic [reverse+audio+image]")
EN_WORD_PATTERN = re.compile(r"[A-Za-z '’.,!?-]+")


def parse_en_word(value: str) -> str:
    """Return the original phrase, or raise ValueError; never silently clean it."""
    if not isinstance(value, str):
        raise ValueError("Expected a plain-text string")
    if not value:
        raise ValueError("Required field is empty")
    if "<" in value or ">" in value:
        raise ValueError("HTML/angle-bracket markup is not allowed in plain text")
    if any(char.isspace() and char != " " for char in value):
        raise ValueError("Only ordinary spaces are allowed; no tabs, newlines or special spaces")
    if value != value.strip(" ") or "  " in value:
        raise ValueError("Use single spaces between words, with no surrounding spaces")
    if not EN_WORD_PATTERN.fullmatch(value):
        unsupported = sorted(set(re.sub(r"[A-Za-z '’.,!?-]", "", value)))
        raise ValueError(f"Unsupported characters: {unsupported!r}")
    if not re.search(r"[A-Za-z]", value):
        raise ValueError("The phrase must contain at least one letter")
    if re.search(r"(?<=[^A-Za-z])['’]|['’](?![A-Za-z]|-)", value):
        raise ValueError("Apostrophes must follow a letter or start the phrase, and precede a letter or hyphen")
    return value
