import os
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from backend import settings
from backend.note_index import NotesDatabase
from backend.storage import SessionStore
from backend.word_completion import WordCompletion
from external_apis.diki_lists import discover_lists
from external_apis.diki_resources import DikiResources
from tools.diki_launchd import configuration
from tools.diki_lookup import ask_save


class TestDataPaths(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.code = self.root / "code"
        self.data = self.root / "personal data"
        self.code.mkdir()
        self.data.mkdir()
        environment = {
            **dict.fromkeys(settings.RETIRED_PATH_VARIABLES, ""),
            "ANKI_FACTORY_DATA_DIR": str(self.data),
        }
        self.environment = patch.dict(os.environ, environment)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        root_patch = patch.object(settings, "ROOT_DIR", self.code)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def test_root_is_required_and_invalid_or_retired_settings_do_not_create_data(self):
        for value in ("", str(self.root / "missing")):
            with patch.dict(os.environ, {"ANKI_FACTORY_DATA_DIR": value}):
                with self.assertRaises(ValueError):
                    settings.database_path()
        with patch.dict(os.environ, {"ANKI_FACTORY_DB_PATH": "old.sqlite3"}):
            with self.assertRaisesRegex(ValueError, "retired path"):
                settings.database_path()
        self.assertEqual(list(self.code.iterdir()), [])

    def test_relative_home_and_dotenv_paths_are_lazy_and_independent_of_cwd(self):
        with patch.dict(os.environ, {"ANKI_FACTORY_DATA_DIR": "../personal data"}):
            self.assertEqual(settings.data_root(), self.data)
        with patch.dict(
            os.environ, {"HOME": str(self.root), "ANKI_FACTORY_DATA_DIR": "~/personal data"}
        ):
            self.assertEqual(settings.data_root(), self.data)
        del os.environ["ANKI_FACTORY_DATA_DIR"]
        (self.code / ".env").write_text(
            "ANKI_FACTORY_DATA_DIR='../personal data'\n", encoding="utf-8"
        )
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            settings.load_environment()
            self.assertEqual(settings.data_root(), self.data)
            self.assertEqual(
                settings.data_path("words_to_add/book.txt"), self.data / "words_to_add/book.txt"
            )
        finally:
            os.chdir(previous)

    def test_browser_capture_prefetch_stores_and_scheduler_share_one_root(self):
        words = self.data / "words_to_add"
        words.mkdir()
        main = words / "words_to_add.txt"
        main.write_bytes(b"same\nsame\n")
        store = SessionStore()
        completions = WordCompletion()
        notes = NotesDatabase()
        with patch("builtins.input", return_value="y"), patch("tools.diki_lookup.console"):
            ask_save("new")
        self.assertEqual(main.read_bytes(), b"same\nsame\nnew\n")
        self.assertEqual(store.list_sessions()[0]["remainingCount"], 3)
        self.assertEqual(discover_lists()[0].words, ["same", "new"])
        self.assertEqual(store.path, completions.db_path)
        self.assertEqual(notes.db_path, store.path)
        self.assertEqual(completions.words_path, main)
        config = configuration()
        self.assertEqual(config["StandardOutPath"], str(self.data / "logs/diki-prefetch.log"))
        transport = Mock()
        with DikiResources(offline=True, get=transport) as resources:
            self.assertEqual(resources.root, self.data / "diki_cache")
        transport.assert_not_called()
        session = store.get_session(store.list_sessions()[0]["id"])
        store.complete_current(session["id"], session["current"]["id"])
        with store._connect() as db:
            reference = db.execute("SELECT backup_path FROM source_resolutions").fetchone()[0]
        self.assertFalse(Path(reference).is_absolute())
        self.assertEqual((self.data / reference).read_bytes(), b"same\nsame\nnew\n")

    def test_moving_root_preserves_workspace_and_cached_resource_without_fetching(self):
        words = self.data / "words_to_add"
        words.mkdir()
        (words / "words_to_add.txt").write_text("take\n", encoding="utf-8")
        store = SessionStore()
        session = store.get_session(store.list_sessions()[0]["id"])
        store.update_session(session["id"], deck_name="English")
        store.replace_current_draft(session["id"], {"word": "take"})
        content = b'<div class="dictionaryEntity"><div class="hws"><span class="hw">take</span></div></div>'
        with DikiResources(offline=True) as resources:
            resources._save("take", "html", content, 200, "https://www.diki.pl/test", True)
        moved = self.root / "moved data"
        self.data.rename(moved)
        os.environ["ANKI_FACTORY_DATA_DIR"] = str(moved)
        reopened = SessionStore().get_session(session["id"])
        self.assertEqual(reopened["current"]["id"], session["current"]["id"])
        self.assertEqual(reopened["deckName"], "English")
        self.assertEqual(reopened["draft"], {"word": "take"})
        transport = Mock()
        with DikiResources(offline=True, get=transport) as resources:
            self.assertEqual(resources.fetch_html("take"), content.decode())
        transport.assert_not_called()
