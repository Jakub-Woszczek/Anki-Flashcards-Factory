import argparse
import os
import threading
import time
import webbrowser
from dotenv import load_dotenv

from RawNotesEditor import RawNotesEditor
from allNotesDb import NotesDatabase

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
        "-e",
        "--run_raw_notes_editor",
        action="store_true",
        help="Runs raw notes editor.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Browser UI host")
    parser.add_argument("--port", default=8000, type=int, help="Browser UI port")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the browser UI server without opening a browser tab.",
    )

    args = parser.parse_args()
    load_dotenv()

    if args.app:
        if args.run_raw_notes_editor:
            raw_notes_editor = RawNotesEditor()
            raw_notes_editor.prepare_raw_notes(os.getenv("PREPROCESSED_WORDS_FILE"))
        else:
            import uvicorn

            if not args.no_browser:
                threading.Timer(
                    0.8,
                    lambda: webbrowser.open(
                        f"http://{args.host}:{args.port}/?v={time.time_ns()}"
                    ),
                ).start()
            from backend.app import app

            server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, reload=False))
            app.state.uvicorn_server = server
            server.run()
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
