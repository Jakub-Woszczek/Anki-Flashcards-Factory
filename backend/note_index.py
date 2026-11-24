import json
import shutil
import sqlite3

from backend.settings import database_path, legacy_index_path
from external_apis.anki_connect import AnkiConnect


class NotesDatabase:
    def __init__(self):
        self.db_path = database_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.anki_api = AnkiConnect()
        self.words_index = set()
        self._initialize()
        self._migrate_legacy_json()
        self.load_db()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS note_index (
                        normalized_word TEXT PRIMARY KEY,
                        en_word TEXT NOT NULL,
                        note_id INTEGER NOT NULL
                    )
                    """
                )
        except sqlite3.Error as error:
            raise DatabaseLoadError("Database could not be initialized") from error

    @staticmethod
    def normalize_word(word: str) -> str:
        return " ".join(word.split()).lower()

    def _migrate_legacy_json(self):
        legacy_path = legacy_index_path()
        if legacy_path is None or not legacy_path.exists():
            return

        with self._connect() as connection:
            has_records = connection.execute("SELECT 1 FROM note_index LIMIT 1").fetchone()
            if has_records:
                return

        try:
            entries = json.loads(legacy_path.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                # Keep the existing ValueError-to-DatabaseLoadError conversion below.
                raise ValueError("Legacy index must be a list")  # noqa: TRY004
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise DatabaseLoadError("Legacy JSON index could not be imported") from error

        with self._connect() as connection:
            for entry in entries:
                word = entry.get("en_word")
                note_id = entry.get("note_id")
                if not isinstance(word, str) or not isinstance(note_id, int):
                    continue
                connection.execute(
                    """
                    INSERT OR IGNORE INTO note_index (normalized_word, en_word, note_id)
                    VALUES (?, ?, ?)
                    """,
                    (self.normalize_word(word), word, note_id),
                )

        backup_path = legacy_path.with_suffix(legacy_path.suffix + ".bak")
        if not backup_path.exists():
            shutil.copy2(legacy_path, backup_path)

    def load_db(self):
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT en_word, note_id FROM note_index ORDER BY en_word"
                ).fetchall()
            self.db = [{"en_word": row["en_word"], "note_id": row["note_id"]} for row in rows]
            self.words_index = {self.normalize_word(entry["en_word"]) for entry in self.db}
        except sqlite3.Error as error:
            raise DatabaseLoadError("Database contents could not be loaded") from error

    def is_in_db(self, word: str) -> bool:
        """Check if a word appears already in db"""
        return self.normalize_word(word) in self.words_index

    def get_note_id(self, word: str) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT note_id FROM note_index WHERE normalized_word = ?",
                (self.normalize_word(word),),
            ).fetchone()
        return row["note_id"] if row else None

    def inventory_discrepancies(self, inventory):
        """Compare the advisory index with Anki's snapshot without changing either."""
        with self._connect() as connection:
            rows = connection.execute("SELECT en_word, note_id FROM note_index").fetchall()
        by_id = {row["note_id"]: row for row in rows}
        by_word = {self.normalize_word(row["en_word"]): row for row in rows}
        notes = {note["noteId"]: note for note in inventory["notes"]}
        issues = []
        for note_id, note in notes.items():
            if note.get("error"):
                continue
            indexed = by_id.get(note_id)
            if indexed is None:
                candidate = by_word.get(self.normalize_word(note["word"]))
                issues.append(
                    {
                        "noteId": note_id,
                        "word": note["word"],
                        "reason": "Word points to a different note in the local index"
                        if candidate is not None
                        else "Note is missing from the local index",
                        "indexedNoteId": candidate["note_id"] if candidate is not None else None,
                    }
                )
        for row in rows:
            note = notes.get(row["note_id"])
            if note is None:
                issues.append(
                    {
                        "noteId": row["note_id"],
                        "word": row["en_word"],
                        "reason": "Indexed note is outside the current Anki inventory",
                    }
                )
            elif not note.get("error") and row["en_word"] != note["word"]:
                issues.append(
                    {
                        "noteId": row["note_id"],
                        "word": note["word"],
                        "reason": "English value differs from the local index",
                        "indexedWord": row["en_word"],
                    }
                )
        return issues

    def add_word(self, note_id: int, en_word: str) -> bool:
        """
        Dodaje jedno słowo do bazy.
        :param note_id: ID notatki w Anki
        :param en_word: angielskie słowo
        :return: True, jeśli dodano. False, jeśli już istniało
        """
        normalized_word = self.normalize_word(en_word)
        if self.is_in_db(en_word):
            print(f"⚠ '{en_word}' Redundant")
            self.anki_api.add_tag_to_note(note_id, "RedundantDB")
            return False

        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO note_index (normalized_word, en_word, note_id)
                    VALUES (?, ?, ?)
                    """,
                    (normalized_word, en_word, note_id),
                )
            except sqlite3.IntegrityError:
                return False

        self.words_index.add(normalized_word)
        self.db.append({"note_id": note_id, "en_word": en_word})
        return True

    def delete_word(self, word_to_remove):
        """
        Delete word from local db
        """
        if not self.is_in_db(word_to_remove):
            raise DatabaseDeleteError(f"Word '{word_to_remove}' not found in local db")

        with self._connect() as connection:
            connection.execute(
                "DELETE FROM note_index WHERE normalized_word = ?",
                (self.normalize_word(word_to_remove),),
            )
        self.load_db()
        print(f"Deleted '{word_to_remove}' from local db")


class DatabaseError(Exception):
    """Bazowy wyjątek dla lokalnej bazy słówek."""


class DatabaseLoadError(DatabaseError):
    """Błąd wczytywania bazy"""


class DatabaseDeleteError(DatabaseError):
    """Błąd usuwania słowa z bazy"""
