from unittest import TestCase

from backend.services import FactoryService, ServiceError
from external_APIs.diki_resources import NoAudio


class FakeTagAnki:
    last_error = None

    def invoke(self, command, **kwargs):
        assert command == "findNotes"
        self.query = kwargs["query"]
        return [101, 102]


class FakeFlagAnki:
    last_error = None

    def invoke(self, command, **kwargs):
        assert command == "findCards"
        self.query = kwargs["query"]
        return [201, 202]

    def cards_info(self, card_ids):
        return [{"cardId": card_id, "note": 900 + card_id} for card_id in card_ids]


class FakeEmptyAnki:
    last_error = None

    def invoke(self, command, **kwargs):
        return []


class FakeDiki:
    last_error = None

    def lookup(self, _word):
        return [["pierwszy", "drugi"]], []

    def get_translations(self, _word):
        return [["pierwszy", "drugi"]]

    def possible_spellings(self, _word):
        return []

    def fetch_audio(self, _word):
        raise NoAudio("Audio unavailable")


class FakeIndex:
    def get_note_id(self, _word):
        return None

    def is_in_db(self, _word):
        return False

    def add_word(self, note_id, word):
        pass


class FakeCommitAnki:
    last_error = None

    def model_schema(self, model_name):
        return {"name": model_name, "fields": ["Front", "Back"]}

    def add_note(self, deck_name, model_name, fields, tags):
        self.call = (deck_name, model_name, fields, tags)
        return 555

    def set_card_flag(self, card_id, flag):
        self.flag_call = (card_id, flag)

    def sync(self):
        return True


class TestReviewStateless(TestCase):
    def test_snapshot_by_tag_returns_note_ids_without_persisting_anything(self):
        service = FactoryService.__new__(FactoryService)
        service.anki = FakeTagAnki()

        result = service.review_snapshot("tag", "TO_EDIT", None)

        self.assertEqual(result["items"], [{"noteId": 101, "cardId": None}, {"noteId": 102, "cardId": None}])
        self.assertEqual(result["filter"], {"kind": "tag", "value": "TO_EDIT", "deckName": None})
        self.assertIn('tag:"TO_EDIT"', service.anki.query)

    def test_snapshot_by_flag_returns_note_and_card_ids(self):
        service = FactoryService.__new__(FactoryService)
        service.anki = FakeFlagAnki()

        result = service.review_snapshot("flag", 1, "English")

        self.assertEqual(result["items"], [{"noteId": 1101, "cardId": 201}, {"noteId": 1102, "cardId": 202}])
        self.assertIn("flag:1", service.anki.query)
        self.assertIn('deck:"English"', service.anki.query)

    def test_snapshot_with_no_matches_raises_404(self):
        service = FactoryService.__new__(FactoryService)
        service.anki = FakeEmptyAnki()

        with self.assertRaises(ServiceError) as context:
            service.review_snapshot("tag", "unused", None)
        self.assertEqual(context.exception.status_code, 404)

    def test_item_lookup_returns_diki_groups_without_a_session(self):
        service = FactoryService.__new__(FactoryService)
        service.diki = FakeDiki()
        service.notes = FakeIndex()
        service.anki = FakeEmptyAnki()

        result = service.review_item_lookup("Streamline", {})

        self.assertEqual(result["word"], "streamline")
        self.assertTrue(result["exactMatch"])
        self.assertIsNone(result["existingNoteId"])

    def test_item_commit_creates_a_note_and_sets_the_card_flag(self):
        service = FactoryService.__new__(FactoryService)
        service.anki = FakeCommitAnki()
        service.notes = FakeIndex()
        service.diki = FakeDiki()

        draft = {"word": "streamline", "groups": [[{"value": "usprawnic", "selected": True}]], "tags": []}
        result = service.review_item_commit(
            note_id=None,
            card_id=42,
            draft=draft,
            action="create",
            remove_tags=[],
            flag=1,
            deck_name="English",
            model_name="Basic",
            field_mapping={"englishField": "Front", "translationField": "Back"},
        )

        self.assertEqual(result["action"], "created")
        self.assertEqual(result["noteId"], 555)
        self.assertEqual(service.anki.call[0], "English")
        self.assertIn("noAudio", service.anki.call[3])
        self.assertEqual(service.anki.flag_call, (42, 1))
