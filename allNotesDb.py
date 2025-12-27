import json
import os
from pathlib import Path

from ankiConnect import AnkiConnect


class NotesDatabase:
    def __init__(self):
        self.db_path = Path(os.getenv("DATABASE_PATH"))
        self.anki_api = AnkiConnect()
        self.db = self.load_db()

    def load_db(self):
        if self.db_path.exists():
            content = self.db_path.read_text(encoding="utf-8").strip()
            if content:
                return json.loads(content)
        return []

    def save_db(self, notes):
        self.db_path.write_text(
            json.dumps(notes, ensure_ascii=False, indent=4), encoding="utf-8"
        )

    def is_redundant(self, word):
        return any(entry["en_word"] == word for entry in self.db)

    def get_redundant(self, words):
        data = self.load_db()
        redundancies = []
        for word in words:
            if any(entry["en_word"] == word for entry in data):
                redundancies.append(word)

        return redundancies

    def add_words(self, words):
        """
        :param words: List of tuples (note_id,word)
        :return:
        """
        db = self.load_db()

        for note_id, word in words:

            if self.is_redundant(word):
                print(f"'{word}' już istnieje w bazie.")
                self.anki_api.add_tag_to_note(note_id, "RedundantDB")
            else:
                entry = {"en_word": word, "note_id": note_id}

                db.append(entry)
                self.save_db(db)

    def add_word(self, note_id: int, en_word: str) -> bool:
        """
        Dodaje jedno słowo do bazy.
        :param note_id: ID notatki w Anki
        :param en_word: angielskie słowo
        :return: True, jeśli dodano. False, jeśli już istniało
        """
        if self.is_redundant(en_word):
            print(f"⚠ '{en_word}' Redundant")
            self.anki_api.add_tag_to_note(note_id, "RedundantDB")
            return False

        entry = {"note_id": note_id, "en_word": en_word}
        self.db.append(entry)
        self.save_db(self.db)
        return True
