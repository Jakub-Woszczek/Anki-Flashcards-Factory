"""Word-list discovery and disk-only offline coverage, without Anki dependencies."""

from dataclasses import dataclass

from backend.settings import data_path, words_directory
from external_apis.diki_resources import DikiResources, normalize_word


@dataclass
class WordList:
    name: str
    words: list[str]
    entries: int
    invalid: int = 0
    error: str | None = None


def discover_lists(directory=None, *, entry_limit: int | None = None) -> list[WordList]:
    if entry_limit is not None and entry_limit < 1:
        raise ValueError("Entry limit must be positive")
    root = (data_path(directory) if directory is not None else words_directory()).resolve()
    paths = sorted(
        root.rglob("*.txt"),
        key=lambda path: (
            path.relative_to(root).as_posix() != "words_to_add.txt",
            path.relative_to(root).as_posix().lower(),
        ),
    )
    lists = []
    for path in paths:
        # Do not traverse a symlink to a file outside the configured source folder.
        if not path.resolve().is_relative_to(root) or not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        try:
            lines = [
                line.strip()
                for line in path.read_text(encoding="utf-8-sig").splitlines()
                if line.strip()
            ]
            # Occurrences, including duplicates/invalid entries, consume positions.
            if entry_limit is not None:
                lines = lines[:entry_limit]
            words, invalid = {}, 0
            for line in lines:
                try:
                    words.setdefault(normalize_word(line), None)
                except ValueError:
                    invalid += 1
            lists.append(WordList(name, list(words), len(lines), invalid))
        except (OSError, UnicodeError) as error:
            lists.append(WordList(name, [], 0, error=str(error)))
    return lists


def coverage(resources: DikiResources, lists=None, *, progress=None):
    if progress is not None:
        progress("Discovering vocabulary lists", 0, None)
    lists = discover_lists() if lists is None else lists
    snapshot = resources.snapshot(profile="background", progress=progress)
    rows = []
    total = sum(len(source.words) for source in lists)
    completed = 0
    if progress is not None:
        progress("Calculating list coverage", completed, total)
    for source in lists:
        row = {
            "name": source.name,
            "entries": source.entries,
            "total": len(source.words),
            "invalid": source.invalid,
            "error": source.error,
            "html": 0,
            "audio": 0,
            "ready": 0,
            "noExactMatch": 0,
            "noAudio": 0,
            "errors": 0,
            "pending": 0,
        }
        for word in source.words:
            html = snapshot.get((word, "html"), {})
            audio = snapshot.get((word, "audio"), {})
            has_html, has_audio = html.get("state") == "ready", audio.get("state") == "ready"
            exact = has_html and bool(html.get("exact_match"))
            row["html"] += int(has_html)
            row["audio"] += int(has_audio)
            row["ready"] += int(exact and has_audio)
            row["noExactMatch"] += int(has_html and not exact)
            row["noAudio"] += int(audio.get("state") == "no_audio")
            row["errors"] += int(any(item.get("state") == "error" for item in (html, audio)))
            row["pending"] += int(
                not has_html or (exact and not has_audio and audio.get("state") != "no_audio")
            )
            completed += 1
            if progress is not None:
                progress("Calculating list coverage", completed, total)
        row["percent"] = round(100 * row["ready"] / row["total"], 1) if row["total"] else 0
        rows.append(row)
    return {
        "lists": rows,
        "lastRun": resources.setting("last_run", profile="background"),
        "cooldownUntil": resources.setting("cooldown_until", 0, profile="background"),
        "cooldownReason": resources.setting("cooldown_reason", profile="background"),
        "pacingMultiplier": resources.setting("pacing_multiplier", 1, profile="background"),
        "requestCounts": resources.setting("request_counts", {}, profile="background"),
        "lastRequest": resources.setting("last_request", profile="background"),
        "offlineOnly": resources.offline,
    }
