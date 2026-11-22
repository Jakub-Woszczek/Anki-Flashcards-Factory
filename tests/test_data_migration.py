import json
import tempfile
from pathlib import Path
from unittest import TestCase

from backend.storage import SessionStore
from backend.word_completion import WordCompletion
from external_apis.diki_resources import DikiResources
from tools.migrate_data import MANIFEST, ORIGINAL_DATABASE, migrate, readonly, retire_source, verify


class TestDataMigration(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name).resolve()
        self.source = root / "code"
        self.destination = root / "data-repo"
        self.words = self.source / "words_to_add"
        self.words.mkdir(parents=True)
        self.destination.mkdir()
        self.main = self.words / "words_to_add.txt"
        self.main.write_bytes(b"\xef\xbb\xbfsame\r\nsame\r\nnew\r\n")
        self.database = self.source / "data/anki_flashcards_factory.sqlite3"
        self.store = SessionStore(self.database, self.words)
        WordCompletion(self.database, self.main)
        self.session = self.store.get_session(self.store.list_sessions()[0]["id"])
        self.store.update_session(self.session["id"], deck_name="English")
        self.store.complete_current(self.session["id"], self.session["current"]["id"])
        # Exercise legacy absolute archive paths, including a previous checkout root.
        with self.store._connect() as db:
            row = db.execute("SELECT entry_id,backup_path FROM source_resolutions").fetchone()
            db.execute(
                "UPDATE source_resolutions SET backup_path=? WHERE entry_id=?",
                ("/previous/checkout/data/" + row["backup_path"], row["entry_id"]),
            )
        with DikiResources(self.source / "data/diki_cache", offline=True) as resources:
            resources._save("same", "html", b"saved HTML", 200, "https://www.diki.pl/same", True)
            resources._save("same", "audio", b"ID3saved audio", 200, "https://www.diki.pl/same.mp3")
            resources.set_setting("cooldown_until", 12345, profile="background")
        (self.source / "Backup.apkg").write_bytes(b"archive")

    def test_migration_preserves_live_bytes_metadata_and_relative_recovery_references(self):
        original = self.main.read_bytes()
        dry = migrate(self.source, self.destination)
        self.assertTrue(dry["dryRun"])
        self.assertEqual(list(self.destination.iterdir()), [])
        migrate(self.source, self.destination, apply=True)
        report = verify(self.destination)
        self.assertEqual(
            (self.destination / "words_to_add/words_to_add.txt").read_bytes(), original
        )
        self.assertTrue((self.destination / ORIGINAL_DATABASE).is_file())
        self.assertTrue(report["rebasedBackups"])
        reopened = SessionStore(
            self.destination / "anki_flashcards_factory.sqlite3", self.destination / "words_to_add"
        )
        self.assertEqual(reopened.get_session(self.session["id"])["deckName"], "English")
        with DikiResources(self.destination / "diki_cache", offline=True) as resources:
            self.assertEqual(resources._read_cached("same", "html"), b"saved HTML")
            self.assertEqual(resources._read_cached("same", "audio"), b"ID3saved audio")
            self.assertEqual(resources.setting("cooldown_until", profile="background"), 12345)
        # Opening initialized stores can change SQLite bytes; retirement checks a fresh
        # verified copy, so this test only checks the durable contents here.
        with readonly(self.destination / "anki_flashcards_factory.sqlite3") as db:
            self.assertTrue(
                db.execute("SELECT backup_path FROM source_resolutions")
                .fetchone()[0]
                .startswith("archives/")
            )

    def test_retirement_rejects_new_capture_then_removes_only_verified_originals(self):
        migrate(self.source, self.destination, apply=True)
        before = self.main.read_bytes()
        self.main.write_bytes(before + b"captured\n")
        with self.assertRaisesRegex(ValueError, "Original changed"):
            retire_source(self.source, self.destination)
        self.assertTrue(self.database.exists())
        self.main.write_bytes(before)
        deprecated = self.source / "external_apis/tmp"
        deprecated.mkdir(parents=True)
        (deprecated / "overflow.mp3").write_bytes(b"obsolete")
        retire_source(self.source, self.destination)
        self.assertFalse(self.main.exists())
        self.assertFalse(self.database.exists())
        self.assertFalse(deprecated.exists())
        verify(self.destination)

    def test_conflicts_pending_removals_and_modified_destination_are_rejected(self):
        (self.destination / "words_to_add").mkdir()
        conflicting = self.destination / "words_to_add/words_to_add.txt"
        conflicting.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            migrate(self.source, self.destination, apply=True)
        conflicting.unlink()
        with self.store._connect() as db:
            db.execute("UPDATE source_resolutions SET state='prepared'")
        with self.assertRaisesRegex(ValueError, "pending"):
            migrate(self.source, self.destination, apply=True)
        with self.store._connect() as db:
            db.execute("UPDATE source_resolutions SET state='consumed'")
        migrate(self.source, self.destination, apply=True)
        conflicting.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            verify(self.destination)
        manifest = json.loads((self.destination / MANIFEST).read_text())
        manifest["files"][0]["path"] = "../outside"
        (self.destination / MANIFEST).write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "escapes"):
            verify(self.destination)
