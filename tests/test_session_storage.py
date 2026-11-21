import json
import sqlite3
import tempfile
import threading
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from backend.storage import SessionStore, SourceChanged
from backend.word_list import append_word, atomic_write


class TestSessionStore(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.words = self.root / "words_to_add.txt"
        self.words.write_bytes(b"first\r\n\r\nfirst\r\nlast")
        self.store = SessionStore(self.root / "factory.sqlite3", self.root)
        self.session_id = self.store.list_sessions()[0]["id"]

    def current(self):
        return self.store.get_session(self.session_id)

    def test_file_is_live_and_only_one_occurrence_is_consumed(self):
        session = self.current()
        entry_id = session["current"]["id"]
        self.store.replace_current_draft(self.session_id, {"word": "resolved"}, entry_id)
        append_word(self.words, "appended")
        live = self.current()
        self.assertEqual(live["remainingCount"], 4)
        self.assertEqual(live["current"]["id"], entry_id)
        self.assertEqual(live["draft"]["word"], "resolved")
        next_session = self.store.complete_current(self.session_id, entry_id)
        self.assertEqual(self.words.read_bytes(), b"\r\nfirst\r\nlast\nappended\n")
        self.assertNotEqual(next_session["current"]["id"], entry_id)
        self.assertEqual(next_session["current"]["word"], "first")
        self.assertEqual(next_session["draft"], {})
        self.assertEqual(next_session["completedCount"], 1)
        self.assertNotIn("queue", next_session)

    def test_stale_draft_or_completion_never_targets_the_next_identical_word(self):
        old = self.current()["current"]["id"]
        self.store.complete_current(self.session_id, old)
        with self.assertRaises(SourceChanged):
            self.store.replace_current_draft(self.session_id, {"word": "stale"}, old)
        self.store.complete_current(self.session_id, old)
        self.assertEqual(self.words.read_bytes(), b"\r\nfirst\r\nlast")
        self.assertEqual(self.current()["completedCount"], 1)

    def test_external_edit_invalidates_draft_and_requires_fresh_entry_id(self):
        old = self.current()["current"]["id"]
        self.store.replace_current_draft(self.session_id, {"word": "first"}, old)
        self.words.write_bytes(b"replacement\nlast\n")
        with self.assertRaises(SourceChanged):
            self.store.require_current(self.session_id, old)
        current = self.current()
        self.assertEqual(current["current"]["word"], "replacement")
        self.assertEqual(current["draft"], {})
        self.assertEqual(self.words.read_bytes(), b"replacement\nlast\n")

    def test_appending_to_unterminated_current_line_is_an_edit_not_new_vocabulary(self):
        self.words.write_bytes(b"first")
        old = self.current()["current"]["id"]
        self.words.write_bytes(b"firstly\n")
        with self.assertRaises(SourceChanged):
            self.store.require_current(self.session_id, old)
        self.assertEqual(self.words.read_bytes(), b"firstly\n")

    def test_books_are_discovered_and_consumed_without_touching_main(self):
        book = self.root / "book.txt"
        book.write_text("causes\ncause\n", encoding="utf-8")
        sources = self.store.list_sessions()
        self.assertEqual([source["name"] for source in sources], ["words_to_add.txt", "book.txt"])
        original = self.words.read_bytes()
        session = self.store.get_session(sources[1]["id"])
        self.store.complete_current(session["id"], session["current"]["id"])
        self.assertEqual(book.read_text(), "cause\n")
        self.assertEqual(self.words.read_bytes(), original)

    def test_same_file_keeps_settings_and_draft_across_restart(self):
        session = self.current()
        self.store.update_session(self.session_id, deck_name="English", model_name="Basic")
        self.store.replace_current_draft(
            self.session_id, {"word": "first"}, session["current"]["id"]
        )
        reopened = SessionStore(self.store.path, self.root)
        self.assertEqual(reopened.list_sessions()[0]["id"], self.session_id)
        session = reopened.get_session(self.session_id)
        self.assertEqual(session["deckName"], "English")
        self.assertEqual(session["draft"], {"word": "first"})
        with reopened._connect() as db:
            entry = json.loads(db.execute("SELECT entry_json FROM sessions").fetchone()[0])
            self.assertNotIn("words", entry)
            self.assertNotIn("queue", entry)

    def test_missing_and_invalid_files_are_reported_without_stale_words(self):
        self.current()
        self.words.unlink()
        summary = self.store.list_sessions()[0]
        self.assertTrue(summary["sourceError"])
        with self.assertRaises(SourceChanged):
            self.current()
        self.words.write_bytes(b"\xff")
        self.assertTrue(self.store.list_sessions()[0]["sourceError"])

    def test_source_path_cannot_escape_folder(self):
        outside = self.root.parent / "outside.txt"
        with self.assertRaises(SourceChanged):
            self.store.source_path(str(outside))
        with self.assertRaises(SourceChanged):
            self.store.source_path("../outside.txt")

    def test_source_alias_is_not_a_second_independent_workspace(self):
        (self.root / "alias.txt").symlink_to(self.words)
        sources = self.store.list_sessions()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["id"], self.session_id)

    def test_two_workspaces_cannot_consume_same_entry_twice(self):
        entry_id = self.current()["current"]["id"]
        other = SessionStore(self.store.path, self.root)
        barrier = threading.Barrier(2)
        outcomes = []

        def consume(store):
            barrier.wait(timeout=3)
            with store.lock():
                try:
                    store.require_current(self.session_id, entry_id)
                    store.complete_current(self.session_id, entry_id)
                    outcomes.append("consumed")
                except SourceChanged:
                    outcomes.append("stale")

        threads = [threading.Thread(target=consume, args=(store,)) for store in (self.store, other)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(outcomes, ["consumed", "stale"])
        self.assertEqual(self.words.read_bytes(), b"\r\nfirst\r\nlast")

    def test_crash_after_removal_preserves_later_cli_append_on_recovery(self):
        entry_id = self.current()["current"]["id"]
        with patch.object(self.store, "_finalize", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                self.store.complete_current(self.session_id, entry_id)
        append_word(self.words, "later capture")
        reopened = SessionStore(self.store.path, self.root)
        self.assertEqual(reopened.get_session(self.session_id)["completedCount"], 1)
        self.assertEqual(self.words.read_bytes(), b"\r\nfirst\r\nlast\nlater capture\n")

    def test_bom_and_missing_final_newline_survive_consumption(self):
        self.words.write_bytes(b"\xef\xbb\xbffirst\r\nlast")
        first = self.current()["current"]["id"]
        self.store.complete_current(self.session_id, first)
        self.assertEqual(self.words.read_bytes(), b"\xef\xbb\xbflast")
        last = self.current()["current"]["id"]
        append_word(self.words, "new")
        self.store.complete_current(self.session_id, last)
        self.assertEqual(self.words.read_bytes(), b"\xef\xbb\xbf\nnew\n")

    def test_failed_replacement_retries_once_after_restart(self):
        entry_id = self.current()["current"]["id"]
        original = self.words.read_bytes()

        def fail_source(path, content):
            if path == self.words:
                raise OSError("disk busy")
            atomic_write(path, content)

        with patch("backend.storage.atomic_write", side_effect=fail_source):
            with self.assertRaises(OSError):
                self.store.complete_current(self.session_id, entry_id)
        self.assertEqual(self.words.read_bytes(), original)
        append_word(self.words, "new")
        reopened = SessionStore(self.store.path, self.root)
        reopened.complete_current(self.session_id, entry_id)
        reopened.complete_current(self.session_id, entry_id)
        self.assertEqual(self.words.read_bytes(), b"\r\nfirst\r\nlast\nnew\n")
        self.assertEqual(reopened.get_session(self.session_id)["completedCount"], 1)

    def test_crash_after_file_replace_does_not_consume_next_duplicate(self):
        self.words.write_bytes(b"same\nsame\n")
        entry_id = self.current()["current"]["id"]
        with patch.object(self.store, "_finalize", side_effect=sqlite3.OperationalError("crash")):
            with self.assertRaises(sqlite3.OperationalError):
                self.store.complete_current(self.session_id, entry_id)
        reopened = SessionStore(self.store.path, self.root)
        session = reopened.get_session(self.session_id)
        self.assertEqual(session["completedCount"], 1)
        self.assertEqual(self.words.read_bytes(), b"same\n")
        reopened.complete_current(self.session_id, entry_id)
        self.assertEqual(self.words.read_bytes(), b"same\n")

    def test_ambiguous_reappend_after_crash_never_deletes_another_occurrence(self):
        self.words.write_bytes(b"same\nsame\n")
        entry_id = self.current()["current"]["id"]
        with patch.object(self.store, "_finalize", side_effect=sqlite3.OperationalError("crash")):
            with self.assertRaises(sqlite3.OperationalError):
                self.store.complete_current(self.session_id, entry_id)
        atomic_write(self.words, b"same\nsame\n")
        reopened = SessionStore(self.store.path, self.root)
        with self.assertRaises(SourceChanged):
            reopened.complete_current(self.session_id, entry_id)
        self.assertEqual(self.words.read_bytes(), b"same\nsame\n")

    def test_cooperating_append_waits_for_atomic_consumption(self):
        entry_id = self.current()["current"]["id"]
        entered, appended = threading.Event(), threading.Event()
        threads = []

        def append():
            entered.set()
            append_word(self.words, "concurrent")
            appended.set()

        def delayed_write(path, content):
            if path == self.words:
                thread = threading.Thread(target=append)
                threads.append(thread)
                thread.start()
                self.assertTrue(entered.wait(2))
                self.assertFalse(appended.wait(0.05))
            atomic_write(path, content)

        with patch("backend.storage.atomic_write", side_effect=delayed_write):
            self.store.complete_current(self.session_id, entry_id)
        for thread in threads:
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(self.words.read_bytes(), b"\r\nfirst\r\nlast\nconcurrent\n")

    def test_legacy_main_settings_are_migrated_but_snapshot_words_are_retired(self):
        legacy_path = self.root / "legacy.sqlite3"
        with sqlite3.connect(legacy_path) as db:
            db.executescript("""
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY, mode TEXT, name TEXT, source TEXT,
                    filter_json TEXT DEFAULT '{}', deck_name TEXT, model_name TEXT,
                    field_mapping_json TEXT DEFAULT '{}', draft_json TEXT DEFAULT '{}',
                    completed_count INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT
                );
                INSERT INTO sessions (id,mode,name,source,deck_name,created_at,updated_at)
                VALUES ('old','add','words_to_add.txt','words_to_add.txt','English','date','date');
                CREATE TABLE session_queue (session_id TEXT, word TEXT);
                INSERT INTO session_queue VALUES ('old','obsolete snapshot word');
            """)
        migrated = SessionStore(legacy_path, self.root)
        session = migrated.get_session("old")
        self.assertEqual(session["deckName"], "English")
        self.assertEqual(session["current"]["word"], "first")
        with migrated._connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM session_queue").fetchone()[0], 0)
