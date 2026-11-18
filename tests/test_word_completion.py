import copy
import tempfile
import threading
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from backend.services import FactoryService, ServiceError
from backend.word_completion import VerificationError, WordCompletion
from backend.word_list import append_word, atomic_write
from external_APIs.diki_resources import NoAudio
from tools.clean_words_to_add import clean


class MemoryAnki:
    last_error = None

    def __init__(self):
        self.notes = {}
        self.decks = {}
        self.cards = {}
        self.add_calls = 0
        self.profile = "Test profile"
        self.bad_read = False
        self.timeout_after_add = False
        self.reply = 123

    def invoke(self, action, **_params):
        self.last_error = None
        if action == "getActiveProfile":
            return self.profile
        if action == "findNotes":
            return list(self.notes)
        raise AssertionError(action)

    def add_note(self, deck, model, fields, tags=None):
        self.add_calls += 1
        self.notes[123] = {"noteId": 123, "modelName": model,
                           "fields": {name: {"value": value} for name, value in fields.items()},
                           "tags": list(tags or [])}
        self.decks[123] = deck
        if self.timeout_after_add:
            self.last_error = "Timed out after Anki accepted the note"
            return None
        return self.reply

    def get_note(self, note_id):
        self.last_error = None
        if self.bad_read:
            self.last_error = "Read-back unavailable"
            return None
        return copy.deepcopy(self.notes.get(note_id))

    def notes_info(self, ids):
        self.last_error = None
        return [copy.deepcopy(self.notes[note_id]) for note_id in ids]

    def get_note_cards(self, note_id):
        self.last_error = None
        return copy.deepcopy(self.cards.get(note_id, [{"cardId": note_id * 10, "deckName": self.decks[note_id]}]))

    def update_note_fields(self, note_id, fields):
        self.notes[note_id]["fields"].update({name: {"value": value} for name, value in fields.items()})

    def add_tag_to_note(self, note_id, tag):
        self.notes[note_id]["tags"].append(tag)

    def remove_tag_from_note(self, note_id, tag):
        self.notes[note_id]["tags"].remove(tag)

    def change_note_deck(self, note_id, deck):
        self.decks[note_id] = deck
        for card in self.cards.get(note_id, []):
            card["deckName"] = deck

    def model_schema(self, model):
        return {"name": model, "fields": ["en_word", "pl_translation", "audio_en"]}

    def sync(self):
        return True


class TestWordCompletion(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.words = self.root / "words.txt"
        self.original = b"Take\r\n\r\nkeep  this\r\n take \r\nlast"
        self.words.write_bytes(self.original)
        self.store = WordCompletion(self.root / "test.sqlite3", self.words)
        self.anki = MemoryAnki()
        self.service = FactoryService.__new__(FactoryService)
        self.service.completions = self.store
        self.service.anki = self.anki
        self.service.notes = Mock()
        self.service.diki = Mock(last_error="Audio unavailable")
        self.service.diki.fetch_audio.side_effect = NoAudio("Audio unavailable")
        self.target = {"deckName": "English", "modelName": "Basic",
                       "fieldMapping": {"englishField": "en_word", "translationField": "pl_translation",
                                        "audioField": "audio_en"}}

    def commit(self, action="create", note_id=None):
        return self.service._perform_commit(
            self.target, {"en_word": "take", "pl_translation": "brać", "audio_en": "[sound:take.mp3]"},
            ["test"], [], action, note_id, "take", None, None)

    def test_read_back_archives_exact_lines_and_preserves_remaining_bytes(self):
        result = self.commit()
        self.assertTrue(result["verified"])
        self.assertEqual(result["removedLines"], 2)
        self.assertEqual(self.words.read_bytes(), b"\r\nkeep  this\r\nlast")
        self.assertEqual(Path(result["backupPath"]).read_bytes(), self.original)
        with self.store.connect() as db:
            archived = db.execute("SELECT original_line FROM word_list_archive ORDER BY line_number").fetchall()
            self.assertEqual([row[0] for row in archived], [b"Take\r\n", b" take \r\n"])
            self.assertEqual(tuple(db.execute("SELECT en_word,note_id FROM note_index").fetchone()), ("take", 123))
            self.assertEqual(db.execute("SELECT state FROM word_saves").fetchone()[0], "cleaned")

    def test_read_back_failure_retains_word_and_retry_does_not_add_again(self):
        self.anki.bad_read = True
        with self.assertRaisesRegex(ServiceError, "Read-back unavailable"):
            self.commit()
        self.assertEqual(self.words.read_bytes(), self.original)
        self.anki.bad_read = False
        self.assertTrue(self.commit()["resumed"])
        self.assertEqual(self.anki.add_calls, 1)

    def test_add_timeout_resolves_saved_payload_without_creating_duplicate(self):
        self.anki.timeout_after_add = True
        with self.assertRaises(ServiceError):
            self.commit()
        self.assertEqual(self.words.read_bytes(), self.original)
        self.assertTrue(self.commit()["verified"])
        self.assertEqual(self.anki.add_calls, 1)

    def test_unknown_save_without_matching_note_never_blindly_retries_add(self):
        self.anki.timeout_after_add = True
        with self.assertRaises(ServiceError):
            self.commit()
        self.anki.notes.clear()
        with self.assertRaisesRegex(ServiceError, "could not be resolved uniquely"):
            self.commit()
        self.assertEqual(self.anki.add_calls, 1)
        self.assertEqual(self.words.read_bytes(), self.original)

    def test_non_integer_id_is_not_success(self):
        self.anki.reply = True
        with self.assertRaises(ServiceError):
            self.commit()
        self.assertEqual(self.words.read_bytes(), self.original)

    def test_every_submitted_field_model_tags_and_deck_are_verified(self):
        self.anki.add_note("English", "Basic", {"en_word": "take", "pl_translation": "brać"}, ["test"])
        expected = {"deckName": "English", "modelName": "Basic",
                    "fields": {"en_word": "take", "pl_translation": "brać"}, "tags": ["test"], "removeTags": ["old"]}
        cases = [lambda: self.anki.notes[123]["fields"]["pl_translation"].update(value="wrong"),
                 lambda: self.anki.notes[123].update(modelName="Wrong model"),
                 lambda: self.anki.notes[123].update(tags=[]),
                 lambda: self.anki.notes[123].update(tags=["test", "old"]),
                 lambda: self.anki.decks.update({123: "Other deck"})]
        for change in cases:
            with self.subTest(change=change):
                self.anki.add_note("English", "Basic", {"en_word": "take", "pl_translation": "brać"}, ["test"])
                change()
                with self.assertRaises(VerificationError):
                    self.store.compare(self.anki, 123, expected)

    def test_field_mismatch_during_save_keeps_list_and_pending_note_id(self):
        real_get = self.anki.get_note

        def corrupted(note_id):
            note = real_get(note_id)
            note["fields"]["pl_translation"]["value"] = "wrong"
            return note
        with patch.object(self.anki, "get_note", side_effect=corrupted):
            with self.assertRaisesRegex(ServiceError, "field pl_translation"):
                self.commit()
        self.assertEqual(self.words.read_bytes(), self.original)
        with self.store.connect() as db:
            row = db.execute("SELECT state,note_id FROM word_saves").fetchone()
            self.assertEqual(tuple(row), ("pending", 123))

    def test_cleanup_failure_is_replayed_after_restart_without_second_add(self):
        def fail_replacement(path, content):
            if path == self.words:
                raise OSError("disk busy")
            atomic_write(path, content)
        with patch("backend.word_completion.atomic_write", side_effect=fail_replacement):
            result = self.commit()
        self.assertTrue(result["cleanupPending"])
        self.assertEqual(self.words.read_bytes(), self.original)
        self.service.completions = WordCompletion(self.store.db_path, self.words)
        result = self.commit()
        self.assertFalse(result["cleanupPending"])
        self.assertEqual(self.anki.add_calls, 1)
        self.assertNotIn(b"take", self.words.read_bytes().lower())

    def test_completed_operation_is_idempotent(self):
        self.commit()
        result = self.commit()
        self.assertTrue(result["resumed"])
        self.assertEqual(self.anki.add_calls, 1)
        self.assertEqual(result["removedLines"], 0)

    def test_readded_word_is_removed_after_fresh_verification_of_previous_save(self):
        self.commit()
        append_word(self.words, "TAKE")
        self.assertEqual(self.commit()["removedLines"], 1)
        self.assertEqual(self.anki.add_calls, 1)
        self.assertNotIn(b"take", self.words.read_bytes().lower())

    def test_update_preserves_existing_audio_and_checks_final_state(self):
        self.anki.add_note("Old deck", "Basic", {"en_word": "take", "pl_translation": "old",
                                                "audio_en": "[sound:old.mp3]"}, ["old"])
        result = self.commit("update", 123)
        self.assertTrue(result["verified"])
        self.assertEqual(self.anki.notes[123]["fields"]["audio_en"]["value"], "[sound:old.mp3]")
        self.assertNotIn("noAudio", self.anki.notes[123]["tags"])
        self.assertEqual(result["removedLines"], 2)

    def test_update_preserves_original_deck_instead_of_queue_target(self):
        self.anki.add_note("Old deck", "Basic", {"en_word": "take", "pl_translation": "old"}, [])
        with patch.object(self.anki, "change_note_deck", wraps=self.anki.change_note_deck) as move:
            result = self.commit("update", 123)
        self.assertTrue(result["verified"])
        self.assertEqual(self.anki.decks[123], "Old deck")
        self.assertEqual(self.anki.notes[123]["fields"]["pl_translation"]["value"], "brać")
        self.assertEqual(result["noteId"], 123)
        move.assert_not_called()

    def test_update_preserves_sibling_cards_in_different_decks(self):
        self.anki.add_note("Old deck", "Basic", {"en_word": "take", "pl_translation": "old"}, [])
        cards = [{"cardId": 1230, "deckName": "Old deck"},
                 {"cardId": 1231, "deckName": "Reverse deck"}]
        self.anki.cards[123] = copy.deepcopy(cards)
        result = self.commit("update", 123)
        self.assertTrue(result["verified"])
        self.assertEqual(self.anki.get_note_cards(123), cards)

    def test_update_retry_verifies_persisted_original_deck_before_cleanup(self):
        self.anki.add_note("Old deck", "Basic", {"en_word": "take", "pl_translation": "old"}, [])
        real_update = self.anki.update_note_fields

        def update_and_move(note_id, fields):
            real_update(note_id, fields)
            self.anki.decks[note_id] = "Unexpected deck"

        with patch.object(self.anki, "update_note_fields", side_effect=update_and_move) as update:
            with self.assertRaisesRegex(ServiceError, "deck"):
                self.commit("update", 123)
            self.assertEqual(self.words.read_bytes(), self.original)
            self.service.completions = WordCompletion(self.store.db_path, self.words)
            with self.assertRaisesRegex(ServiceError, "deck"):
                self.commit("update", 123)
            self.assertEqual(self.words.read_bytes(), self.original)
            self.anki.decks[123] = "Old deck"
            result = self.commit("update", 123)
            update.assert_called_once()
        self.assertTrue(result["resumed"])
        self.assertTrue(result["verified"])
        self.assertEqual(self.anki.decks[123], "Old deck")

    def test_update_requires_readable_original_card_decks(self):
        self.anki.add_note("Old deck", "Basic", {"en_word": "take", "pl_translation": "old"}, [])
        with patch.object(self.anki, "get_note_cards", return_value=[]):
            with self.assertRaisesRegex(ServiceError, "deck"):
                self.commit("update", 123)
        self.assertEqual(self.anki.notes[123]["fields"]["pl_translation"]["value"], "old")
        self.assertEqual(self.words.read_bytes(), self.original)

    def test_review_update_preserves_original_deck(self):
        self.anki.add_note("Old deck", "Basic", {"en_word": "take", "pl_translation": "old"}, [])
        result = self.service.review_item_commit(
            note_id=123, card_id=None,
            draft={"word": "take", "groups": [[{"value": "brać", "selected": True}]], "tags": []},
            action="update", remove_tags=[], flag=None, deck_name=self.target["deckName"],
            model_name=self.target["modelName"], field_mapping=self.target["fieldMapping"],
        )
        self.assertTrue(result["verified"])
        self.assertEqual(self.anki.decks[123], "Old deck")

    def test_skip_never_removes_from_source(self):
        self.service.sessions = Mock()
        self.service.skip_current("session")
        self.assertEqual(self.words.read_bytes(), self.original)

    def test_custom_card_is_read_back_before_removing_word(self):
        self.service.session = lambda _: {"mode": "add", "current": {"word": "take"}, "draft": {}}
        self.service.sessions = Mock()
        result = self.service.create_custom_card("session", "English", "Basic", {"en_word": "take"})
        self.assertTrue(result["verified"])
        self.assertEqual(result["removedLines"], 2)
        self.service.sessions.complete_current.assert_called_once_with("session")

    def test_failed_custom_verification_does_not_advance_queue(self):
        self.service.session = lambda _: {"mode": "add", "current": {"word": "take"}, "draft": {}}
        self.service.sessions = Mock()
        self.anki.bad_read = True
        with self.assertRaises(ServiceError):
            self.service.create_custom_card("session", "English", "Basic", {"en_word": "take"})
        self.service.sessions.complete_current.assert_not_called()
        self.assertEqual(self.words.read_bytes(), self.original)

    def test_cleanup_pending_keeps_session_item(self):
        self.service.sessions = Mock()
        session = {**self.target, "mode": "add", "current": {"word": "take"},
                   "draft": {"word": "take", "groups": [[{"value": "brać", "selected": True}]], "tags": []}}
        self.service.session = lambda _: session
        self.service.notes.get_note_id.return_value = None
        with patch.object(self.store, "cleanup", side_effect=OSError("disk busy")):
            result = self.service.commit_current("session", "create", [], None)
        self.assertTrue(result["cleanupPending"])
        self.assertIs(result["session"], session)
        self.service.sessions.complete_current.assert_not_called()

    def test_legacy_cleanup_confirms_notes_and_archives_duplicates(self):
        self.anki.add_note("English", "Basic", {"en_word": "take"}, [])
        result = clean(self.anki, self.store)
        self.assertEqual(result["verifiedWords"], 1)
        self.assertEqual(result["removedLines"], 2)
        self.assertEqual(clean(self.anki, self.store)["verifiedWords"], 0)

    def test_profile_change_before_verification_retains_list(self):
        save, _ = self.store.prepare("Different profile", "take", {}, "create", note_id=123)
        with self.assertRaisesRegex(VerificationError, "profile changed"):
            self.store.verify(self.anki, save["id"])
        self.assertEqual(self.words.read_bytes(), self.original)

    def test_unverified_operations_cannot_remove_lines(self):
        save, _ = self.store.prepare("Test profile", "take", {}, "create")
        with self.assertRaises(VerificationError):
            self.store.cleanup([save["id"]])
        self.assertEqual(self.words.read_bytes(), self.original)

    def test_bom_is_preserved_when_first_line_is_removed(self):
        self.words.write_bytes(b"\xef\xbb\xbfTake\r\nkeep\r\n")
        self.commit()
        self.assertEqual(self.words.read_bytes(), b"\xef\xbb\xbfkeep\r\n")

    def test_concurrent_append_waits_for_cleanup_and_is_not_lost(self):
        entered = threading.Event()
        appended = threading.Event()
        threads = []

        def append():
            entered.set()
            append_word(self.words, "new word")
            appended.set()

        def delayed_write(path, content):
            if path == self.words:
                thread = threading.Thread(target=append)
                threads.append(thread)
                thread.start()
                self.assertTrue(entered.wait(2))
                self.assertFalse(appended.wait(0.05))
            atomic_write(path, content)

        with patch("backend.word_completion.atomic_write", side_effect=delayed_write):
            self.commit()
        for thread in threads:
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.assertTrue(appended.is_set())
        self.assertTrue(self.words.read_bytes().endswith(b"last\nnew word\n"))
        self.assertFalse(append_word(self.words, "NEW   WORD"))
