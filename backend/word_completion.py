"""Read-after-write verification and a durable, replayable word-list archive."""

import hashlib
import html
import json
import re
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from backend.settings import configured_words_to_add_path, database_path
from backend.word_list import atomic_write, list_lock, normalize_word


class VerificationError(Exception):
    pass


def field_word(value: str) -> str:
    return normalize_word(re.sub(r"<[^>]+>", " ", html.unescape(value)))


def utc_now():
    return datetime.now(UTC).isoformat()


class WordCompletion:
    def __init__(self, db_path=None, words_path=None):
        self.db_path = Path(db_path or database_path()).resolve()
        self.words_path = Path(words_path or configured_words_to_add_path()).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS word_saves (
                    id TEXT PRIMARY KEY, profile TEXT NOT NULL, word TEXT NOT NULL,
                    intent TEXT NOT NULL, reason TEXT NOT NULL, note_id INTEGER,
                    expected_json TEXT NOT NULL, observed_json TEXT,
                    state TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
                    verified_at TEXT, cleaned_at TEXT, backup_path TEXT
                );
                CREATE INDEX IF NOT EXISTS word_saves_pending
                    ON word_saves(profile, word, intent, reason);
                CREATE TABLE IF NOT EXISTS word_list_archive (
                    save_id TEXT NOT NULL REFERENCES word_saves(id),
                    source TEXT NOT NULL, line_number INTEGER NOT NULL,
                    original_line BLOB NOT NULL,
                    PRIMARY KEY(save_id, source, line_number, original_line)
                );
                CREATE TABLE IF NOT EXISTS note_index (
                    normalized_word TEXT PRIMARY KEY, en_word TEXT NOT NULL,
                    note_id INTEGER NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.db_path, timeout=30)) as db:
            db.row_factory = sqlite3.Row
            with db:
                yield db

    def lock(self):
        return list_lock(self.db_path)

    @staticmethod
    def profile(anki):
        profile = anki.invoke("getActiveProfile")
        if anki.last_error or not isinstance(profile, str) or not profile:
            raise VerificationError(anki.last_error or "Could not identify the active Anki profile")
        return profile

    def prepare(self, profile, word, intent, reason, *, expected=None, note_id=None):
        digest = hashlib.sha256(
            json.dumps(intent, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        with self.connect() as db:
            row = db.execute(
                """SELECT * FROM word_saves
                WHERE profile=? AND word=? AND intent=? AND reason=?
                AND (state != 'cleaned' OR reason IN ('create', 'custom'))
                ORDER BY created_at DESC LIMIT 1""",
                (profile, normalize_word(word), digest, reason),
            ).fetchone()
            if row:
                return dict(row), True
            save_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO word_saves
                (id,profile,word,intent,reason,note_id,expected_json,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (
                    save_id,
                    profile,
                    normalize_word(word),
                    digest,
                    reason,
                    note_id,
                    json.dumps(expected or {}, ensure_ascii=False),
                    utc_now(),
                ),
            )
        return self.get(save_id), False

    def get(self, save_id):
        with self.connect() as db:
            return dict(db.execute("SELECT * FROM word_saves WHERE id=?", (save_id,)).fetchone())

    def submitted(self, save_id, note_id, expected):
        if type(note_id) is not int or note_id <= 0:
            raise VerificationError("Anki did not return a valid note ID; word retained")
        with self.connect() as db:
            db.execute(
                "UPDATE word_saves SET note_id=?,expected_json=? WHERE id=?",
                (note_id, json.dumps(expected, ensure_ascii=False), save_id),
            )

    def expect(self, save_id, expected):
        with self.connect() as db:
            db.execute(
                "UPDATE word_saves SET expected_json=? WHERE id=?",
                (json.dumps(expected, ensure_ascii=False), save_id),
            )

    def recover(self, anki, save):
        """An addNote timeout may have created a note. Never blindly submit it twice."""
        if save["note_id"]:
            return
        expected = json.loads(save["expected_json"])
        ids = anki.invoke("findNotes", query="")
        if anki.last_error or ids is None:
            raise VerificationError(
                anki.last_error or "Could not resolve the interrupted Anki save"
            )
        notes = anki.notes_info(ids)
        if anki.last_error:
            raise VerificationError(anki.last_error)
        matches = []
        for note in notes:
            if note.get("modelName") != expected.get("modelName") or any(
                note.get("fields", {}).get(name, {}).get("value") != value
                for name, value in expected.get("fields", {}).items()
            ):
                continue
            try:
                self.compare(anki, note["noteId"], expected)
            except VerificationError:
                continue
            matches.append(note["noteId"])
        if len(matches) != 1:
            raise VerificationError(
                "The previous save has no confirmed note ID and could not be resolved uniquely. "
                "Check Anki before saving again; the word has been retained."
            )
        self.submitted(save["id"], matches[0], expected)

    @staticmethod
    def card_decks(cards):
        """Capture validated card identities/decks with JSON-stable string keys."""
        if not isinstance(cards, list) or not cards:
            raise VerificationError("Could not read existing card decks; word retained")
        decks = {}
        for card in cards:
            if not isinstance(card, dict):
                raise VerificationError("Could not identify existing card decks; word retained")
            card_id, deck = card.get("cardId"), card.get("deckName")
            if (
                type(card_id) is not int
                or card_id <= 0
                or not isinstance(deck, str)
                or not deck
                or str(card_id) in decks
            ):
                raise VerificationError("Could not identify existing card decks; word retained")
            decks[str(card_id)] = deck
        return decks

    @staticmethod
    def compare(anki, note_id, expected):
        note = anki.get_note(note_id)
        if anki.last_error or not note or note.get("noteId") != note_id:
            raise VerificationError(anki.last_error or f"Note {note_id} was not found on read-back")
        differences = []
        if note.get("modelName") != expected.get("modelName"):
            differences.append("note type")
        for name, value in expected.get("fields", {}).items():
            actual = note.get("fields", {}).get(name, {}).get("value")
            # Only normalize line-ending transport differences, never field contents.
            if not isinstance(actual, str) or actual.replace("\r\n", "\n") != value.replace(
                "\r\n", "\n"
            ):
                differences.append(f"field {name}")
        tags = set(note.get("tags", []))
        if not set(expected.get("tags", [])) <= tags:
            differences.append("missing tags")
        if set(expected.get("removeTags", [])) & tags:
            differences.append("tags not removed")
        if "cardDecks" in expected or expected.get("deckName"):
            cards = anki.get_note_cards(note_id)
            if anki.last_error or not cards:
                differences.append("deck")
            elif "cardDecks" in expected:
                if WordCompletion.card_decks(cards) != expected["cardDecks"]:
                    differences.append("card decks")
            elif any(card.get("deckName") != expected["deckName"] for card in cards):
                differences.append("deck")
        if differences:
            raise VerificationError(
                f"Note {note_id} verification failed: {', '.join(differences)}. Word retained."
            )
        return note

    def verify(self, anki, save_id):
        save = self.get(save_id)
        if self.profile(anki) != save["profile"]:
            raise VerificationError("Anki profile changed; word retained")
        if type(save["note_id"]) is not int or save["note_id"] <= 0:
            raise VerificationError("No confirmed Anki note ID; word retained")
        note = self.compare(anki, save["note_id"], json.loads(save["expected_json"]))
        if self.profile(anki) != save["profile"]:
            raise VerificationError("Anki profile changed during read-back; word retained")
        # Persist confirmation and the local index together, before touching the list.
        with self.connect() as db:
            db.execute(
                """UPDATE word_saves SET observed_json=?,verified_at=?,
                state='verified' WHERE id=?""",
                (json.dumps(note, ensure_ascii=False), utc_now(), save_id),
            )
            db.execute(
                """INSERT INTO note_index VALUES (?,?,?)
                ON CONFLICT(normalized_word) DO UPDATE SET note_id=excluded.note_id,
                en_word=excluded.en_word""",
                (save["word"], save["word"], save["note_id"]),
            )
        return note

    def cleanup(self, save_ids):
        """Archive lines before replacement; replay is safe after either commit boundary."""
        saves = [self.get(save_id) for save_id in save_ids]
        if any(save["state"] not in {"verified", "cleaned"} for save in saves):
            raise VerificationError("Unverified words cannot be removed")
        saves = {save["word"]: save for save in saves if save["state"] == "verified"}
        if not saves:
            return {"removedLines": 0}
        with list_lock(self.words_path):
            if not self.words_path.exists():
                raise OSError(f"Word list does not exist: {self.words_path}")
            content = self.words_path.read_bytes()
            remaining, removed = [], []
            for number, line in enumerate(content.splitlines(keepends=True), 1):
                word = normalize_word(line.decode("utf-8").lstrip("\ufeff"))
                if word in saves:
                    removed.append((saves[word]["id"], str(self.words_path), number, line))
                else:
                    remaining.append(line)
            backup = None
            if removed:
                directory = self.db_path.parent / "archives"
                directory.mkdir(parents=True, exist_ok=True)
                backup = directory / f"words-to-add-{uuid.uuid4()}.txt.bak"
                atomic_write(backup, content)
                with self.connect() as db:
                    db.executemany(
                        "INSERT OR IGNORE INTO word_list_archive VALUES (?,?,?,?)", removed
                    )
                    db.executemany(
                        "UPDATE word_saves SET backup_path=? WHERE id=?",
                        [(str(backup), save["id"]) for save in saves.values()],
                    )
                replacement = b"".join(remaining)
                if content.startswith(b"\xef\xbb\xbf") and not replacement.startswith(
                    b"\xef\xbb\xbf"
                ):
                    replacement = b"\xef\xbb\xbf" + replacement
                atomic_write(self.words_path, replacement)
            with self.connect() as db:
                db.executemany(
                    "UPDATE word_saves SET state='cleaned',cleaned_at=? WHERE id=?",
                    [(utc_now(), save["id"]) for save in saves.values()],
                )
        return {"removedLines": len(removed), "backupPath": str(backup) if backup else None}

    def finish(self, anki, save_id):
        self.verify(anki, save_id)
        # Interactive saves have no implicit main-file cleanup. The source workspace
        # consumes its exact entry separately; stateless review consumes no source.
        return {"verified": True, "cleanupPending": False}
