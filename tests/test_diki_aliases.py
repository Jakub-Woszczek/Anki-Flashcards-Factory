import copy
from pathlib import Path
from typing import Any
from unittest import TestCase
from unittest.mock import Mock

from backend.note_index import NotesDatabase
from backend.services import FactoryService, ServiceError
from external_apis.diki_api import DikiApi, resolve_lookup
from external_apis.diki_resources import NoAudio
from tests.completion_helpers import install_completion, install_source
from tests.test_diki_headwords import entry
from tests.test_word_completion import MemoryAnki

HTML = (Path(__file__).parent / "diki_cases" / "anaesthetic-variants.html").read_text(
    encoding="utf-8"
)


class TestEntryAlternatives(TestCase):
    def test_selected_spelling_and_ordered_identity_are_separate(self):
        for query in ("Anesthetic", "anesthetic", "anaesthetic"):
            result = resolve_lookup(HTML, query)
            self.assertEqual(result.word, "anaesthetic" if query == "anaesthetic" else "anesthetic")
            self.assertEqual(
                result.matching_headwords,
                [
                    {"word": "anaesthetic", "caseSensitive": False},
                    {"word": "anesthetic", "caseSensitive": False},
                ],
            )
            self.assertEqual(result.translations, [["środek znieczulający"], ["znieczulający"]])

    def test_only_selected_entities_supply_aliases_and_case_is_checked_per_alias(self):
        document = (
            entry("remedy", "lekarstwo").replace(
                '<span class="hw">remedy</span>',
                '<span class="hw">remedy</span><span class="hw">Cure</span>',
            )
            + entry("cure", "leczyć")
            + entry("other", "inne")
        )
        result = resolve_lookup(document, "remedy")
        self.assertFalse(result.case_sensitive)
        self.assertEqual(
            result.matching_headwords,
            [
                {"word": "remedy", "caseSensitive": False},
                {"word": "Cure", "caseSensitive": True},
            ],
        )


class TestAliasWorkflow(TestCase):
    def setUp(self):
        self.service: Any = FactoryService.__new__(FactoryService)
        install_completion(self, self.service)
        self.words = self.service.completions.words_path
        self.words.write_text("Anesthetic\nanesthetic\nanaesthetic\n", encoding="utf-8")
        session = install_source(self.service)
        self.session = self.service.sessions.update_session(
            session["id"],
            deck_name="English::D1",
            model_name="Basic",
            field_mapping={
                "englishField": "en_word",
                "translationField": "pl_translation",
                "audioField": "audio_en",
            },
        )
        self.anki: Any = MemoryAnki()
        self.anki.find_notes_by_field = Mock(wraps=self.anki.find_notes_by_field)
        self.anki.update_note_fields = Mock(wraps=self.anki.update_note_fields)
        self.service.anki = self.anki
        index = NotesDatabase.__new__(NotesDatabase)
        index.db_path = self.service.completions.db_path
        index.anki_api = Mock()
        index.load_db()
        self.service.notes = index
        self.resources = Mock(fetch_html=Mock(return_value=HTML))
        self.resources.fetch_audio.side_effect = NoAudio("Audio unavailable")
        self.service.diki = DikiApi(self.resources)

    def add_existing(self, word="anaesthetic", note_id=123):
        self.anki.notes[note_id] = {
            "noteId": note_id,
            "modelName": "Basic",
            "tags": ["old"],
            "fields": {
                "en_word": {"value": word},
                "pl_translation": {"value": "stare tłumaczenie"},
                "audio_en": {"value": "[sound:old.mp3]"},
            },
        }
        self.anki.decks[note_id] = "English::Learned"
        self.anki.cards[note_id] = [
            {"cardId": note_id * 10, "deckName": "English::Learned"},
            {"cardId": note_id * 10 + 1, "deckName": "English::Reverse"},
        ]

    def lookup(self, **kwargs):
        return self.service.lookup_current(
            self.session["id"], entry_id=self.session["current"]["id"], **kwargs
        )

    def draft(self):
        return self.service.session(self.session["id"])["draft"]

    def select_translation(self):
        draft = self.draft()
        draft["groups"][0][0]["selected"] = True
        draft["tags"] = ["IMAGE"]
        self.service.update_current_draft(
            self.session["id"], draft, entry_id=self.session["current"]["id"]
        )
        return draft

    def commit(self, action="update"):
        return self.service.commit_current(
            self.session["id"], action, [], None, entry_id=self.session["current"]["id"]
        )

    def test_dictionary_first_headword_wins_even_if_resolved_spelling_also_exists(self):
        self.add_existing()
        self.add_existing("anesthetic", 124)
        self.service.notes.add_word(124, "anesthetic")
        result = self.lookup()
        self.assertEqual(result["word"], "anesthetic")
        self.assertEqual(result["existingNoteId"], 123)
        self.assertEqual(
            [call.args[1] for call in self.anki.find_notes_by_field.call_args_list], ["anaesthetic"]
        )

    def test_later_alias_is_searched_when_first_has_no_valid_match(self):
        self.add_existing("anesthetic")
        result = self.lookup()
        self.assertEqual(result["existingNoteId"], 123)
        self.assertEqual(
            [call.args[1] for call in self.anki.find_notes_by_field.call_args_list],
            ["anaesthetic", "anesthetic"],
        )

    def test_stale_index_and_broad_anki_results_do_not_match_unrelated_notes(self):
        self.add_existing("unrelated")
        self.service.notes.add_word(123, "anaesthetic")
        self.anki.find_notes_by_field.return_value = [123]
        self.assertIsNone(self.lookup()["existingNoteId"])

    def test_alias_refresh_locks_english_decks_and_audio_and_consumes_only_original_occurrence(
        self,
    ):
        self.add_existing()
        self.assertEqual(self.lookup()["existingNoteId"], 123)
        self.select_translation()
        preview = self.service.preview_current(
            self.session["id"], entry_id=self.session["current"]["id"]
        )
        self.assertEqual(preview["word"], "anesthetic")
        self.assertEqual(preview["fields"]["en_word"], "anaesthetic")
        diff = self.service.existing_note(self.session["id"])
        self.assertFalse(
            next(row["changed"] for row in diff["fieldDiff"] if row["field"] == "en_word")
        )
        result = self.commit()
        self.assertEqual((result["action"], result["noteId"]), ("updated", 123))
        self.assertEqual(self.anki.add_calls, 0)
        self.assertNotIn("en_word", self.anki.update_note_fields.call_args.args[1])
        self.assertEqual(self.anki.notes[123]["fields"]["en_word"]["value"], "anaesthetic")
        self.assertEqual(
            self.anki.notes[123]["fields"]["pl_translation"]["value"], "środek znieczulający"
        )
        self.assertEqual(self.anki.notes[123]["fields"]["audio_en"]["value"], "[sound:old.mp3]")
        self.assertEqual(self.anki.get_note_cards(123)[1]["deckName"], "English::Reverse")
        self.assertEqual(self.words.read_text(), "anesthetic\nanaesthetic\n")
        self.service.notes.load_db()
        self.assertTrue(self.service.notes.is_in_db("anaesthetic"))
        self.assertEqual(self.service.notes.get_note_id("anaesthetic"), 123)
        self.assertIsNone(self.service.notes.get_note_id("anesthetic"))

    def test_legacy_draft_refresh_preserves_choices_tags_and_target(self):
        self.lookup()
        original = self.select_translation()
        original.pop("matchingHeadwords")
        original["flag"] = 3
        original["targetOverride"] = {"deckName": "English::Override"}
        original["existingNoteId"] = None
        self.service.sessions.replace_current_draft(self.session["id"], original)
        self.add_existing()
        result = self.lookup(preserve_draft=True)
        self.assertEqual(result["existingNoteId"], 123)
        self.assertEqual(result["draft"]["groups"], original["groups"])
        self.assertEqual(result["draft"]["tags"], ["IMAGE"])
        self.assertEqual(result["draft"]["flag"], 3)
        self.assertEqual(result["draft"]["targetOverride"], original["targetOverride"])
        self.assertEqual(result["draft"]["resolvedWord"], "anesthetic")
        tampered = copy.deepcopy(result["draft"])
        tampered["matchingHeadwords"] = [{"word": "unrelated", "caseSensitive": False}]
        self.service.update_current_draft(
            self.session["id"], tampered, entry_id=self.session["current"]["id"]
        )
        self.assertEqual(self.draft()["matchingHeadwords"], result["matchingHeadwords"])

    def test_note_changed_after_lookup_is_rejected_before_update(self):
        self.add_existing()
        self.lookup()
        self.select_translation()
        self.anki.notes[123]["fields"]["en_word"]["value"] = "unrelated"
        with self.assertRaisesRegex(ServiceError, "different English word"):
            self.commit()
        self.anki.update_note_fields.assert_not_called()
        self.assertEqual(self.words.read_text(), "Anesthetic\nanesthetic\nanaesthetic\n")

    def test_create_rechecks_aliases_if_note_appeared_after_lookup(self):
        self.assertIsNone(self.lookup()["existingNoteId"])
        self.select_translation()
        self.add_existing()
        with self.assertRaisesRegex(ServiceError, "already has an indexed note"):
            self.commit("create")
        self.assertEqual(self.anki.add_calls, 0)

    def test_stateless_review_rederives_aliases_instead_of_trusting_client_values(self):
        self.add_existing("unrelated")
        self.lookup()
        draft = self.select_translation()
        draft["matchingHeadwords"] = [{"word": "unrelated", "caseSensitive": False}]
        with self.assertRaisesRegex(ServiceError, "different English word"):
            self.service.review_item_commit(
                123,
                None,
                draft,
                "update",
                [],
                None,
                "English",
                "Basic",
                self.session["fieldMapping"],
            )
        self.anki.update_note_fields.assert_not_called()

    def test_stateless_review_refresh_preserves_original_note_and_does_not_consume_queue(self):
        self.add_existing()
        result = self.service.review_item_lookup("anesthetic", self.session["fieldMapping"])
        self.assertEqual(result["existingNoteId"], 123)
        draft = {
            "word": result["word"],
            "resolvedWord": result["resolvedWord"],
            "lookupQuery": result["lookupQuery"],
            "matchingHeadwords": result["matchingHeadwords"],
            "groups": result["groups"],
            "existingNoteId": 123,
        }
        draft["groups"][0][0]["selected"] = True
        preview = self.service.review_item_preview(
            draft, "English::D1", "Basic", self.session["fieldMapping"]
        )
        self.assertEqual(preview["fields"]["en_word"], "anaesthetic")
        saved = self.service.review_item_commit(
            123,
            None,
            draft,
            "update",
            [],
            None,
            "English::D1",
            "Basic",
            self.session["fieldMapping"],
        )
        self.assertEqual(saved["noteId"], 123)
        self.assertEqual(self.anki.notes[123]["fields"]["en_word"]["value"], "anaesthetic")
        self.assertEqual(self.words.read_text(), "Anesthetic\nanesthetic\nanaesthetic\n")

    def test_alias_update_recovers_against_preserved_spelling_without_second_mutation(self):
        self.add_existing()
        self.lookup()
        self.select_translation()
        update = self.anki.update_note_fields

        def update_then_lose_readback(note_id, fields):
            MemoryAnki.update_note_fields(self.anki, note_id, fields)
            self.anki.bad_read = True

        update.side_effect = update_then_lose_readback
        with self.assertRaisesRegex(ServiceError, "Save not confirmed"):
            self.commit()
        self.anki.bad_read = False
        update.side_effect = None
        saved = self.commit()
        self.assertTrue(saved["resumed"])
        self.assertEqual(saved["noteId"], 123)
        self.assertEqual(update.call_count, 1)
        self.assertEqual(self.anki.notes[123]["fields"]["en_word"]["value"], "anaesthetic")
        self.assertEqual(self.words.read_text(), "anesthetic\nanaesthetic\n")

    def test_case_distinct_alternative_cannot_use_other_entitys_lowercase_spelling(self):
        document = entry("remedy", "lekarstwo").replace(
            '<span class="hw">remedy</span>',
            '<span class="hw">remedy</span><span class="hw">Cure</span>',
        ) + entry("cure", "leczyć")
        self.resources.fetch_html.return_value = document
        self.add_existing("cure")
        # Anki searches can be case-insensitive; validate the returned field values.
        self.anki.find_notes_by_field.return_value = [123]
        self.assertIsNone(self.lookup(requested_word="remedy")["existingNoteId"])

    def test_failed_alias_search_is_not_reported_as_new_note(self):
        def unavailable(*_args):
            self.anki.last_error = "Anki unavailable"
            return []

        self.anki.find_notes_by_field.side_effect = unavailable
        with self.assertRaisesRegex(ServiceError, "Could not check existing Anki notes"):
            self.lookup()
