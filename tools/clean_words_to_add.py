"""Read-only report by default; --apply verifies and archives before removing lines."""

import argparse
import json
import sqlite3

from dotenv import load_dotenv

from backend.settings import ROOT_DIR, configured_words_to_add_path
from backend.word_completion import VerificationError, WordCompletion, field_word
from backend.word_list import normalize_word
from external_apis.anki_connect import AnkiConnect


def clean(anki, store, *, resume=False):
    profile = store.profile(anki)
    with store.lock():
        if resume:
            with store.connect() as db:
                saves = [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM word_saves WHERE profile=? AND state!='cleaned'", (profile,)
                    )
                ]
            for save in saves:
                store.recover(anki, save)
                store.verify(anki, save["id"])
            return {
                "profile": profile,
                "verifiedWords": len(saves),
                **store.cleanup([save["id"] for save in saves]),
            }

        words = {
            normalize_word(line)
            for line in store.words_path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        }
        notes = matching_notes(anki, words)
        saves = []
        for word, note in notes.items():
            expected = {
                "modelName": note["modelName"],
                "fields": {"en_word": note["fields"]["en_word"]["value"]},
            }
            save, _ = store.prepare(
                profile,
                word,
                {"noteId": note["noteId"], **expected},
                "already_in_anki",
                expected=expected,
                note_id=note["noteId"],
            )
            store.verify(anki, save["id"])
            saves.append(save["id"])
        if store.profile(anki) != profile:
            raise VerificationError("Anki profile changed; list was not modified")
        result = store.cleanup(saves)
        remaining = [
            line
            for line in store.words_path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        if any(normalize_word(line) in notes for line in remaining):
            raise VerificationError("A confirmed word remains in the list")
        return {
            "profile": profile,
            "verifiedWords": len(saves),
            **result,
            "remainingLines": len(remaining),
            "remainingUnique": len({normalize_word(line) for line in remaining}),
        }


def matching_notes(anki, words):
    ids = anki.invoke("findNotes", query="en_word:*")
    if anki.last_error or ids is None:
        raise VerificationError(anki.last_error or "Could not read Anki notes")
    notes = anki.notes_info(ids)
    if anki.last_error:
        raise VerificationError(anki.last_error)
    matches = {}
    for note in notes:
        word = field_word(note.get("fields", {}).get("en_word", {}).get("value", ""))
        if word in words:
            matches.setdefault(word, note)
    return matches


def main():
    load_dotenv(ROOT_DIR / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Archive and remove verified words")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Retry outstanding saved operations (requires --apply)",
    )
    args = parser.parse_args()
    if args.resume and not args.apply:
        parser.error("--resume requires --apply")
    anki = AnkiConnect()
    try:
        if args.apply:
            result = clean(anki, WordCompletion(), resume=args.resume)
        else:
            path = configured_words_to_add_path()
            lines = [
                line for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()
            ]
            matches = matching_notes(anki, {normalize_word(line) for line in lines})
            result = {
                "dryRun": True,
                "matchingWords": len(matches),
                "matchingLines": sum(normalize_word(line) in matches for line in lines),
            }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (VerificationError, OSError, sqlite3.Error, UnicodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
