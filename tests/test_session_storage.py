import tempfile
from pathlib import Path
from unittest import TestCase

from backend.storage import SessionStore


class TestSessionStore(TestCase):
    def test_add_session_keeps_order_and_current_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(Path(directory) / "factory.sqlite3")
            created = store.create_add_session(["first", "", "second"], "import")

            self.assertEqual(created["remainingCount"], 2)
            self.assertEqual(created["current"]["word"], "first")

            draft = {"word": "first", "groups": [], "tags": ["TO_EDIT"]}
            persisted = store.replace_current_draft(created["id"], draft)
            self.assertEqual(persisted["draft"], draft)

            advanced = store.complete_current(created["id"])
            self.assertEqual(advanced["current"]["word"], "second")
            self.assertEqual(advanced["completedCount"], 1)

    def test_editing_away_the_current_word_discards_its_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(Path(directory) / "factory.sqlite3")
            created = store.create_add_session(["first", "second"], "import")
            store.replace_current_draft(created["id"], {"word": "first", "groups": []})

            edited = store.replace_add_queue(created["id"], ["second", "third"])

            self.assertEqual([item["word"] for item in edited["queue"]], ["second", "third"])
            self.assertEqual(edited["draft"], {})
            self.assertEqual(edited["current"]["word"], "second")

    def test_editing_after_the_current_word_keeps_its_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(Path(directory) / "factory.sqlite3")
            created = store.create_add_session(["first", "second"], "import")
            draft = {"word": "first", "groups": []}
            store.replace_current_draft(created["id"], draft)

            edited = store.replace_add_queue(created["id"], ["first", "third"])

            self.assertEqual(edited["draft"], draft)
            self.assertEqual(edited["current"]["word"], "first")

    def test_deleting_a_session_removes_its_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(Path(directory) / "factory.sqlite3")
            created = store.create_add_session(["first", "second"], "import")

            store.delete_session(created["id"])

            with self.assertRaises(KeyError):
                store.get_session(created["id"])
            with store._connect() as connection:
                remaining = connection.execute(
                    "SELECT COUNT(*) FROM session_queue WHERE session_id = ?", (created["id"],)
                ).fetchone()[0]
            self.assertEqual(remaining, 0)
