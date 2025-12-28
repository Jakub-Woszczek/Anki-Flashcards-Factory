import json
import os
from pathlib import Path

from ankiConnect import AnkiConnect


class NotesDatabase:
    def __init__(self):
        db_path = os.getenv("DATABASE_PATH")
        if not db_path:
            print(db_path)
            raise DatabasePathError("DATABASE_PATH environment variable is not set")

        self.db_path = Path(db_path)
        self.anki_api = AnkiConnect()

        self.db = None
        self.words_index = set()
        self.load_db()

    def load_db(self):
        if not self.db_path.exists():
            raise DatabasePathError(f"Database file does not exist: {self.db_path}")

        try:
            content = self.db_path.read_text(encoding="utf-8").strip()
            self.db = json.loads(content) if content else []

            if not isinstance(self.db, list):
                raise DatabaseLoadError("Database must be a list")

            self.words_index = {entry["en_word"] for entry in self.db}

        except json.decoder.JSONDecodeError as e:
            raise DatabaseLoadError("Database contents could not be decoded") from e
        except OSError as e:
            raise DatabaseLoadError("Database file could not be read") from e

    def save_db(self):
        self.db_path.write_text(
            json.dumps(self.db, ensure_ascii=False, indent=4), encoding="utf-8"
        )

    def is_in_db(self, word: str) -> bool:
        """Check if a word appears already in db"""
        return word in self.words_index

    def get_redundant(self, words_list):
        """
        Return all words that appear on words_list and in db
        """
        data = self.db
        redundancies = []
        for word in words_list:
            if any(entry["en_word"] == word for entry in data):
                redundancies.append(word)

        return redundancies

    def __add_words(self, words):
        """
        Function that adds words to db. Words is list of tuples (note_id,word),it is
        """

        for note_id, word in words:

            if self.is_in_db(word):
                print(f"'{word}' już istnieje w bazie.")
            else:
                entry = {"en_word": word, "note_id": note_id}
                self.db.append(entry)
                print(f"Dodano '{word}' do bazy.")

        self.save_db()

    def add_word(self, note_id: int, en_word: str) -> bool:
        """
        Dodaje jedno słowo do bazy.
        :param note_id: ID notatki w Anki
        :param en_word: angielskie słowo
        :return: True, jeśli dodano. False, jeśli już istniało
        """
        if self.is_in_db(en_word):
            print(f"⚠ '{en_word}' Redundant")
            self.anki_api.add_tag_to_note(note_id, "RedundantDB")
            return False

        entry = {"note_id": note_id, "en_word": en_word}
        self.db.append(entry)
        self.save_db()
        return True

    def __get_all_notes_content(self):
        decks_names = self.anki_api.get_subdecks()
        all_notes_ids = [
            note_id
            for deck_name in decks_names
            for note_id in self.anki_api.notes_ids_from_deck(deck_name)
        ]
        all_notes_content = self.anki_api.harness_cards_content(all_notes_ids)
        return all_notes_content

    def db_inspection(self):
        """
        Function inspects for errors in database local and in anki app, show all differences between them like:
        - word appears in local db but not in anki
        - word appears in anki but not in local db
        - if there is redundant word in local db
        """

        all_notes_content = self.__get_all_notes_content()
        all_notes_words = [
            note["fields"]["en_word"]["value"] for note in all_notes_content
        ]

        print("\nWords from local db that are not in anki:")
        for item in self.db:
            if item["en_word"] not in all_notes_words:
                print(item["en_word"])

        print("\nWords from anki db that are not in local db:")
        for word in all_notes_words:
            if not self.is_in_db(word):
                print(word)

        print("\nRedundant words in local db:")
        seen = set()
        for entry in self.db:
            w = entry["en_word"]
            if w in seen:
                print(w)
            else:
                seen.add(w)

    def delete_word(self, word_to_remove, save_db=True):
        """
        Delete word from local db
        """
        if not self.is_in_db(word_to_remove):
            raise DatabaseDeleteError(f"Word '{word_to_remove}' not found in local db")

        self.db = [item for item in self.db if item.get("en_word") != word_to_remove]
        self.save_db() if save_db else None
        print(f"Deleted '{word_to_remove}' from local db")

    def delete_multiple_words(self):
        """
        Deletes words from local db in a loop.
        User can enter words one by one; entering 'q' quits the loop.
        """

        while True:
            word_to_remove = input(
                "Podaj słowo do usunięcia (lub 'q' aby zakończyć): "
            ).strip()
            if word_to_remove.lower() == "q":
                break
            self.delete_word(word_to_remove, save_db=False)

        self.save_db()

    def update_local_db(self):
        """
        Adds words to local db from anki that are not in local db.
        """
        all_notes_content = self.__get_all_notes_content()
        all_notes_entries = [
            (note["noteId"], note["fields"]["en_word"]["value"])
            for note in all_notes_content
        ]
        missing_notes_entries = [
            (n[0], n[1]) for n in all_notes_entries if not self.is_in_db(n[1])
        ]
        self.__add_words(missing_notes_entries)


class DatabaseError(Exception):
    """Bazowy wyjątek dla lokalnej bazy słówek."""


class DatabaseLoadError(DatabaseError):
    """Błąd wczytywania bazy"""


class DatabasePathError(DatabaseError):
    """Błąd ścieżki do pliku bazy."""


class DatabaseDeleteError(DatabaseError):
    """Błąd usuwania słowa z bazy"""
