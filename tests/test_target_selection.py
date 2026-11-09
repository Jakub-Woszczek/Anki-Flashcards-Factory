from unittest import TestCase

from backend.services import FactoryService
from external_APIs.diki_resources import NoAudio


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


class FakeDuplicateAnki:
    last_error = None

    def find_notes_by_field(self, field_name, value):
        self.query = (field_name, value)
        return [12]

    def notes_info(self, _note_ids):
        return [{"noteId": 12, "fields": {"en_word": {"value": "streamline"}}}]


class FakeCustomCardAnki:
    last_error = None

    def model_schema(self, model_name):
        return {"name": model_name, "fields": ["Front", "Back"]}

    def add_note(self, deck_name, model_name, fields):
        self.call = (deck_name, model_name, fields)
        return 99

    def sync(self):
        return True


class FakeCustomSessions:
    def __init__(self):
        self.completed = None

    def complete_current(self, session_id):
        self.completed = session_id
        return {"id": session_id, "remainingCount": 0}


class FakeDuplicateActionAnki:
    last_error = None

    def suspend_note_cards(self, note_id):
        self.suspended_note_id = note_id

    def delete_note(self, note_id):
        self.deleted_note_id = note_id

    def sync(self):
        return True


class FakeDuplicateActionIndex:
    def __init__(self):
        self.note_id = 99
        self.deleted_words = []

    def get_note_id(self, _word):
        return self.note_id

    def delete_word(self, word):
        self.deleted_words.append(word)
        self.note_id = None


class FakeDuplicateActionSessions:
    def complete_current(self, session_id):
        self.completed = session_id
        return {"id": session_id, "remainingCount": 0}

    def replace_current_draft(self, session_id, draft):
        self.replaced = (session_id, draft)
        return {"id": session_id, "draft": draft}


class FakeFlaggedCreateAnki:
    last_error = None

    def add_note(self, _deck_name, _model_name, _fields, _tags):
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
        service = FactoryService.__new__(FactoryService)
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
        service = FactoryService.__new__(FactoryService)
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
        service = FactoryService.__new__(FactoryService)
        service.anki = FakeCustomCardAnki()
        service.notes = FakeIndex()
        service.sessions = FakeCustomSessions()
        service.session = lambda _session_id: {
            "mode": "add",
            "current": {"word": "streamline"},
            "draft": {},
        }

        result = service.create_custom_card(
            "session-1",
            "English::test",
            "Basic",
            {"Front": "streamline", "Back": "custom meaning"},
        )

        self.assertEqual(service.anki.call, ("English::test", "Basic", {"Front": "streamline", "Back": "custom meaning"}))
        self.assertEqual(service.notes.added, [(99, "streamline")])
        self.assertEqual(service.sessions.completed, "session-1")
        self.assertEqual(result["noteId"], 99)

    def test_suspending_a_duplicate_note_advances_the_queue(self):
        service = FactoryService.__new__(FactoryService)
        service.anki = FakeDuplicateActionAnki()
        service.sessions = FakeDuplicateActionSessions()
        service.session = lambda _session_id: {
            "mode": "add",
            "current": {"word": "streamline"},
            "draft": {"word": "streamline", "existingNoteId": 99},
        }

        result = service.suspend_duplicate_note("session-1")

        self.assertEqual(service.anki.suspended_note_id, 99)
        self.assertEqual(service.sessions.completed, "session-1")
        self.assertEqual(result["action"], "suspended duplicate")

    def test_deleting_a_duplicate_note_clears_the_local_index_and_draft(self):
        service = FactoryService.__new__(FactoryService)
        service.anki = FakeDuplicateActionAnki()
        service.notes = FakeDuplicateActionIndex()
        service.sessions = FakeDuplicateActionSessions()
        service.session = lambda _session_id: {
            "mode": "add",
            "current": {"word": "streamline"},
            "draft": {"word": "streamline", "existingNoteId": 99},
        }

        result = service.delete_duplicate_note("session-1")

        self.assertEqual(service.anki.deleted_note_id, 99)
        self.assertEqual(service.notes.deleted_words, ["streamline"])
        self.assertEqual(service.sessions.replaced, ("session-1", {"word": "streamline", "existingNoteId": None}))
        self.assertEqual(result["action"], "deleted duplicate")

    def test_creating_a_note_flags_every_generated_card(self):
        service = FactoryService.__new__(FactoryService)
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
