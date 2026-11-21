from typing import Any
from unittest import TestCase
from unittest.mock import Mock

from backend.services import FactoryService
from external_apis.diki_resources import NoAudio
from tests.completion_helpers import ReadBackAnki, install_completion, install_source


class FakeAnki:
    last_error = None

    def deck_names(self):
        return ["English", "English::A1", "English::A1::Stories", "Polish"]


class FakeIndex:
    def __init__(self):
        self.added = []

    def get_note_id(self, _word):
        return None

    def is_in_db(self, _word):
        return False

    def add_word(self, note_id, word):
        self.added.append((note_id, word))

    def load_db(self):
        pass


class FakeDuplicateAnki:
    last_error = None

    def find_notes_by_field(self, field_name, value):
        self.query = (field_name, value)
        return [12]

    def notes_info(self, _note_ids):
        return [{"noteId": 12, "fields": {"en_word": {"value": "streamline"}}}]


class FakeCustomCardAnki(ReadBackAnki):
    last_error = None

    def model_schema(self, model_name):
        return {"name": model_name, "fields": ["Front", "Back"]}

    def add_note(self, deck_name, model_name, fields):
        self.call = (deck_name, model_name, fields)
        return 99

    def sync(self):
        return True


class FakeFlaggedCreateAnki(ReadBackAnki):
    last_error = None

    def add_note(self, _deck_name, _model_name, _fields, _tags):
        self.call = (_deck_name, _model_name, _fields, _tags)
        return 99

    def set_note_cards_flag(self, note_id, flag):
        self.flagged = (note_id, flag)

    def sync(self):
        return True


class FakeNoAudioDiki:
    last_error = "Audio unavailable"

    def fetch_audio(self, _word):
        raise NoAudio("Audio unavailable")


class TestTargetSelection(TestCase):
    def test_deck_tree_nests_anki_deck_paths(self):
        service: Any = FactoryService.__new__(FactoryService)
        service.anki = FakeAnki()

        self.assertEqual(
            service.deck_tree(),
            [
                {
                    "name": "English",
                    "fullName": "English",
                    "children": [
                        {
                            "name": "A1",
                            "fullName": "English::A1",
                            "children": [
                                {
                                    "name": "Stories",
                                    "fullName": "English::A1::Stories",
                                    "children": [],
                                }
                            ],
                        }
                    ],
                },
                {"name": "Polish", "fullName": "Polish", "children": []},
            ],
        )

    def test_card_override_does_not_change_the_batch_target(self):
        session = {
            "deckName": "English::A1",
            "modelName": "Basic",
            "fieldMapping": {"englishField": "Front", "translationField": "Back"},
        }
        draft = {
            "targetOverride": {
                "deckName": "English::Stories",
                "modelName": "Story note",
                "fieldMapping": {"englishField": "Word", "translationField": "Meaning"},
            }
        }

        target = FactoryService._card_target(session, draft)

        self.assertEqual(target["deckName"], "English::Stories")
        self.assertEqual(target["modelName"], "Story note")
        self.assertTrue(target["isOverride"])
        self.assertEqual(session["deckName"], "English::A1")
        self.assertEqual(session["modelName"], "Basic")

    def test_anki_duplicate_repairs_a_missing_local_index_entry(self):
        service: Any = FactoryService.__new__(FactoryService)
        service.anki = FakeDuplicateAnki()
        service.notes = FakeIndex()

        note_id = service._find_existing_note_id(
            "streamline",
            {"fieldMapping": {"englishField": "en_word"}},
        )

        self.assertEqual(note_id, 12)
        self.assertEqual(service.anki.query, ("en_word", "streamline"))
        self.assertEqual(service.notes.added, [(12, "streamline")])

    def test_selected_break_marker_controls_the_next_sense_separator(self):
        self.assertEqual(
            FactoryService.translation_html([["pierwszy", "<br>"], ["drugi"]]),
            "pierwszy<br>\ndrugi",
        )
        self.assertEqual(
            FactoryService.translation_html([["pierwszy"], ["drugi"]]),
            "pierwszy, drugi",
        )

    def test_custom_card_uses_all_schema_fields_and_advances_the_queue(self):
        service: Any = FactoryService.__new__(FactoryService)
        install_completion(self, service)
        service.anki = FakeCustomCardAnki()
        service.notes = FakeIndex()
        session = install_source(service)

        result = service.create_custom_card(
            session["id"],
            "English::test",
            "Basic",
            {"Front": "streamline", "Back": "custom meaning"},
        )

        self.assertEqual(
            service.anki.call,
            ("English::test", "Basic", {"Front": "streamline", "Back": "custom meaning"}),
        )
        with service.completions.connect() as db:
            self.assertEqual(
                tuple(db.execute("SELECT note_id,en_word FROM note_index").fetchone()),
                (99, "streamline"),
            )
        self.assertEqual(result["session"]["current"]["word"], "take")
        self.assertEqual(service.completions.words_path.read_text(), "take\n")
        self.assertEqual(result["noteId"], 99)

    def test_discarding_entry_with_existing_note_advances_without_changing_anki(self):
        service: Any = FactoryService.__new__(FactoryService)
        install_completion(self, service)
        service.anki = Mock()
        session = install_source(service)
        service.sessions.replace_current_draft(
            session["id"], {"word": "streamline", "existingNoteId": 99}
        )

        result = service.discard_current(session["id"], entry_id=session["current"]["id"])

        self.assertEqual(service.anki.mock_calls, [])
        self.assertEqual(result["current"]["word"], "take")
        self.assertEqual(result["remainingCount"], 1)
        self.assertEqual(service.completions.words_path.read_text(), "take\n")

    def test_creating_a_note_flags_every_generated_card(self):
        service: Any = FactoryService.__new__(FactoryService)
        install_completion(self, service)
        service.anki = FakeFlaggedCreateAnki()
        service.notes = FakeIndex()
        service.diki = FakeNoAudioDiki()

        service._perform_commit(
            {"deckName": "English", "modelName": "Basic", "fieldMapping": {}},
            {"Front": "streamline", "Back": "custom meaning"},
            [],
            [],
            "create",
            None,
            "streamline",
            4,
            None,
        )

        self.assertEqual(service.anki.flagged, (99, 4))
