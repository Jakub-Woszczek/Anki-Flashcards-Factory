import argparse
import os
from dotenv import load_dotenv

from RawNotesEditor import RawNotesEditor
from allNotesDb import NotesDatabase
from preparedNotesAdder import FlashcardApp

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", action="store_true", help="Run the main app")
    parser.add_argument(
        "--db", action="store_true", help="Run database redundancy check"
    )

    parser.add_argument("-i", action="store_true", help="Run database inspection")
    parser.add_argument(
        "-dm",
        "--delete_multiple",
        action="store_true",
        help="Run database function to delete multiple words",
    )
    parser.add_argument("-d", "--to_delete", help="Delete word from local db")
    parser.add_argument(
        "-u",
        "--update_db",
        action="store_true",
        help="Adds words to local db from anki that are not in local db.",
    )
    parser.add_argument(
        "-t",
        "--run_functional_test",
        action="store_true",
        help="Runs functional tests.",
    )
    parser.add_argument(
        "-e",
        "--run_raw_notes_editor",
        action="store_true",
        help="Runs raw notes editor.",
    )

    args = parser.parse_args()
    load_dotenv()

    if args.app:
        if args.run_functional_test:
            app = FlashcardApp(
                os.getenv("TEST_WORDS_PATH"),
                os.getenv("ANKI_DECK_PATH_TEST"),
                write_to_db=False,
            )
        elif args.run_raw_notes_editor:
            raw_notes_editor = RawNotesEditor()
            raw_notes_editor.prepare_raw_notes(os.getenv("PREPROCESSED_WORDS_FILE"))
        else:
            app = FlashcardApp(
                os.getenv("PREPARED_WORDS_PATH"), os.getenv("ANKI_DECK_PATH")
            )
    elif args.db:
        db = NotesDatabase()
        if args.i:
            db.db_inspection()
        elif args.to_delete:
            db.delete_word(args.to_delete)
        elif args.delete_multiple:
            db.delete_multiple_words()
        elif args.update_db:
            db.update_local_db()
