"""Saved Anki vocabulary inventory, shared by coverage and remote preparation."""

import json
from datetime import UTC, datetime

from backend.note_contracts import NOTE_TYPES, parse_en_word
from backend.settings import data_path, diki_coverage_inventory
from external_apis.diki_remote import atomic_file
from external_apis.diki_resources import normalize_word


def export_inventory(api, *, cancelled=lambda: False):
    words = {}
    invalid = []
    inventory_notes = []
    seen = set()
    checked = 0

    def read(action, **params):
        if cancelled():
            raise InterruptedError("Inventory reconciliation was stopped")
        result = api.invoke(action, **params)
        if result is None:
            raise ValueError(api.last_error or f"AnkiConnect returned no result for {action}")
        return result

    profile = read("getActiveProfile")
    if not isinstance(profile, str) or not profile:
        raise ValueError("AnkiConnect did not identify the active profile")
    for model in NOTE_TYPES:
        # Missing-Diki and image-only models are outside the documented scope.
        ids = read("findNotes", query="note:" + json.dumps(model))
        if (
            not isinstance(ids, list)
            or any(type(note_id) is not int or note_id <= 0 for note_id in ids)
            or len(set(ids)) != len(ids)
            or seen.intersection(ids)
        ):
            raise ValueError("Invalid or changing note inventory; saved inventory was not replaced")
        seen.update(ids)
        for start in range(0, len(ids), 250):
            batch = ids[start : start + 250]
            notes = read("notesInfo", notes=batch)
            if len(notes) != len(batch) or {note.get("noteId") for note in notes} != set(batch):
                raise ValueError("Incomplete notesInfo response; inventory was not replaced")
            for note in notes:
                if note.get("modelName") != model:
                    raise ValueError(
                        "A note changed type during export; inventory was not replaced"
                    )
                checked += 1
                value = note.get("fields", {}).get("en_word", {}).get("value")
                record = {
                    "noteId": note["noteId"],
                    "word": value if isinstance(value, str) else None,
                    "model": model,
                }
                try:
                    word = parse_en_word(value)
                    normalize_word(word)
                except ValueError as error:
                    invalid.append({"noteId": note["noteId"], "reason": str(error)})
                    record["error"] = str(error)
                else:
                    words.setdefault(word, None)
                inventory_notes.append(record)
    if read("getActiveProfile") != profile:
        raise ValueError("Anki profile changed during export; inventory was not replaced")
    return {
        "version": 2,
        "createdAt": datetime.now(UTC).isoformat(),
        "profile": profile,
        "noteTypes": list(NOTE_TYPES),
        "checked": checked,
        "words": list(words),
        "notes": inventory_notes,
        "invalidCount": len(invalid),
        "invalidSamples": invalid[:20],
    }


def save_inventory(inventory):
    atomic_file(diki_coverage_inventory(), json.dumps(inventory, ensure_ascii=False).encode())


def load_inventory():
    path = diki_coverage_inventory()
    if not path.exists():
        return {"words": [], "invalidCount": 0, "available": False}
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("version") not in (1, 2)
        or not isinstance(value.get("words"), list)
    ):
        raise ValueError("Invalid coverage inventory; explicitly export/import it again")
    for word in value["words"]:
        parse_en_word(word)
        normalize_word(word)
    if value["version"] == 2:
        notes = value.get("notes")
        if not isinstance(notes, list):
            raise ValueError("Invalid note inventory; explicitly export it again")
        seen = set()
        valid_words = {}
        invalid = 0
        for note in notes:
            if (
                not isinstance(note, dict)
                or type(note.get("noteId")) is not int
                or note["noteId"] <= 0
                or note["noteId"] in seen
                or note.get("model") not in NOTE_TYPES
            ):
                raise ValueError("Invalid note inventory; explicitly export it again")
            seen.add(note["noteId"])
            try:
                raw_word = note.get("word")
                if not isinstance(raw_word, str):
                    # Match the stored-field parser's ValueError contract.
                    raise ValueError("Expected a plain-text string")  # noqa: TRY004
                word = parse_en_word(raw_word)
                normalize_word(word)
            except ValueError:
                invalid += 1
                if not isinstance(note.get("error"), str) or not note["error"]:
                    raise ValueError("Invalid note inventory error; export it again") from None
            else:
                if note.get("error"):
                    raise ValueError("Unexpected note inventory error; export it again")
                valid_words.setdefault(word, None)
        if (
            value.get("checked") != len(notes)
            or value.get("invalidCount") != invalid
            or value["words"] != list(valid_words)
        ):
            raise ValueError("Inconsistent note inventory; explicitly export it again")
    return {**value, "available": True}


def import_inventory(path):
    words = {}
    for line in data_path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            word = parse_en_word(line)
            normalize_word(word)
            words.setdefault(word, None)
    value = {
        "version": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "words": list(words),
        "invalidCount": 0,
        "source": "explicit-word-file",
    }
    save_inventory(value)
    return value
