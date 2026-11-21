import tempfile
from pathlib import Path
from typing import Any
from unittest import TestCase
from unittest.mock import Mock, patch

from backend.services import FactoryService, ServiceError
from backend.word_list import append_word
from external_apis.diki_api import DikiApi, parse_translations, resolve_lookup
from external_apis.diki_audio import discover_audio_urls
from external_apis.diki_lists import discover_lists
from external_apis.diki_resources import CacheMiss, DikiResources
from tests.completion_helpers import install_completion, install_source
from tests.test_diki_resources import MP3, response
from tools.diki_lookup import run_lookup
from tools.diki_prefetch import run_batch

CASES = Path(__file__).parent / "diki_cases"
BASEL = (CASES / "basel.html").read_text(encoding="utf-8")
ASTRAY = (CASES / "lead-astray.html").read_text(encoding="utf-8")


def entry(word, translation, audio=""):
    # Small controlled homograph fixture; recording paths are deliberately distinct.
    return f"""<div class="dictionaryEntity"><div class="hws"><span class="hw">{word}</span>
        <span data-audio-url="/images-common/en/mp3/{audio}.mp3"></span></div>
        <ol class="foreignToNativeMeanings"><li><span class="hw">{translation}</span></li></ol></div>"""


POLISH = entry("polish", "polerować", "polish-verb") + entry("Polish", "polski", "polish-language")
TURKEY = entry("Turkey", "Turcja", "turkey-country") + entry("turkey", "indyk", "turkey-bird")


class TestDikiHeadwords(TestCase):
    def test_resolves_dictionary_spelling_and_preserves_all_meaning_groups(self):
        for query in ("Basel", "basel", " BASEL "):
            result = resolve_lookup(BASEL, query)
            self.assertEqual(result.word, "Basel")
            self.assertEqual(result.translations, [["Bazylea (miasto w Szwajcarii)"]])
        self.assertEqual(resolve_lookup(BASEL, "Basle").word, "Basle")
        result = resolve_lookup(ASTRAY, "lead astray")
        self.assertEqual(result.word, "lead somebody astray")
        self.assertEqual(
            result.translations,
            [
                ["prowadzić kogoś na manowce", "sprowadzać kogoś na złą drogę"],
                ["wprowadzić kogoś w błąd"],
            ],
        )
        self.assertEqual(
            discover_audio_urls(ASTRAY, "lead astray"),
            ["https://www.diki.pl/images-common/en/mp3/lead_somebody_astray.mp3"],
        )

    def test_exact_case_selects_one_entry_and_uppercase_ambiguity_requires_choice(self):
        for document, cases, ambiguous in [
            (
                POLISH,
                [("Polish", "polski", "polish-language"), ("polish", "polerować", "polish-verb")],
                "POLISH",
            ),
            (
                TURKEY,
                [("Turkey", "Turcja", "turkey-country"), ("turkey", "indyk", "turkey-bird")],
                "TURKEY",
            ),
        ]:
            for word, translation, audio in cases:
                result = resolve_lookup(document, word)
                self.assertEqual(result.word, word)
                self.assertTrue(result.case_sensitive)
                self.assertEqual(result.translations, [[translation]])
                self.assertEqual(parse_translations(document, word), [[translation]])
                self.assertEqual(
                    discover_audio_urls(document, word),
                    [f"https://www.diki.pl/images-common/en/mp3/{audio}.mp3"],
                )
            result = resolve_lookup(document, ambiguous)
            self.assertIsNone(result.word)
            self.assertEqual(set(result.suggestions), {case[0] for case in cases})
            self.assertEqual(discover_audio_urls(document, ambiguous), [])

    def test_multiple_unmatched_entries_are_suggestions_not_an_automatic_first_choice(self):
        result = resolve_lookup(BASEL + ASTRAY, "unknown")
        self.assertIsNone(result.word)
        self.assertIn("Basel", result.suggestions)
        self.assertIn("lead somebody astray", result.suggestions)
        self.assertNotIn("Basel Convention", result.suggestions)

    def test_cli_saves_resolved_headword_instead_of_query(self):
        for document, query, expected in [
            (BASEL, "basel", "Basel"),
            (ASTRAY, "lead astray", "lead somebody astray"),
        ]:
            api = DikiApi(Mock(fetch_html=Mock(return_value=document)))
            with (
                patch("tools.diki_lookup.ask_save") as save,
                patch("tools.diki_lookup.display_meanings"),
            ):
                run_lookup(api, query)
                save.assert_called_once_with(expected)


class TestHeadwordResources(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.get = Mock(
            side_effect=lambda url, **kwargs: response(MP3 if "/mp3/" in url else BASEL.encode())
        )
        self.resources = DikiResources(self.root / "cache", get=self.get, interval=0)
        self.addCleanup(self.resources.close)

    def test_request_and_cache_keys_preserve_case_and_legacy_lowercase_html_is_reusable(self):
        self.resources.fetch_html(" Basel ")
        self.assertIn("q=Basel", self.get.call_args.args[0])
        self.assertNotEqual(
            self.resources.path("Polish", "html"), self.resources.path("polish", "html")
        )
        self.resources._save("basel", "html", BASEL.encode(), 200, "legacy", True)
        self.resources.offline = True
        self.assertEqual(DikiApi(self.resources).lookup("BASEL").word, "Basel")
        self.assertEqual(self.get.call_count, 1)

    def test_legacy_case_ambiguous_html_does_not_alias_a_different_query(self):
        self.resources._save("polish", "html", POLISH.encode(), 200, "legacy", True)
        self.resources.offline = True
        with self.assertRaises(CacheMiss):
            self.resources.fetch_html("Polish")
        self.get.assert_not_called()

    def test_legacy_audio_is_reused_only_when_its_source_matches_the_entry(self):
        self.resources._save("basel", "html", BASEL.encode(), 200, "legacy", True)
        self.resources._save(
            "basel", "audio", MP3, 200, "https://www.diki.pl/images-common/en/mp3/basel.mp3"
        )
        self.resources.offline = True
        self.assertEqual(self.resources.fetch_html("Basel"), BASEL)
        self.assertEqual(self.resources.fetch_audio("Basel"), MP3)
        self.get.assert_not_called()
        self.resources._save("polish", "html", POLISH.encode(), 200, "legacy", True)
        self.resources._save(
            "polish",
            "audio",
            MP3,
            200,
            "https://www.diki.pl/images-common/en/mp3/polish-language.mp3",
        )
        with self.assertRaises(CacheMiss):
            self.resources.fetch_audio("polish")
        self.assertEqual(self.resources.snapshot()[("polish", "audio")]["state"], "pending")

    def test_prefetch_reinterprets_old_no_exact_match_without_redownloading_html(self):
        self.resources._save("lead astray", "html", ASTRAY.encode(), 200, "legacy", False)
        from external_apis.diki_lists import WordList

        result = run_batch(self.resources, [WordList("main", ["lead astray"], 1)])
        self.assertEqual(result["audio"], 1)
        self.assertEqual(self.get.call_count, 1)
        self.assertTrue(self.get.call_args.args[0].endswith("/lead_somebody_astray.mp3"))
        self.resources.offline = True
        self.assertEqual(DikiApi(self.resources).lookup("lead astray").word, "lead somebody astray")
        self.assertEqual(self.resources.fetch_audio("lead somebody astray"), MP3)
        self.assertEqual(self.get.call_count, 1)

    def test_prefetch_discovery_preserves_case_distinct_words(self):
        folder = self.root / "words"
        folder.mkdir()
        (folder / "words_to_add.txt").write_text("Polish\npolish\nPolish\n", encoding="utf-8")
        self.assertEqual(discover_lists(folder)[0].words, ["Polish", "polish"])
        path = folder / "capture.txt"
        self.assertTrue(append_word(path, "Polish"))
        self.assertTrue(append_word(path, "polish"))
        self.assertFalse(append_word(path, "Polish"))


class TestHeadwordWorkflow(TestCase):
    def test_preview_save_index_and_source_consumption_keep_resolved_identity(self):
        for original, document, expected in [
            ("basel", BASEL, "Basel"),
            ("lead astray", ASTRAY, "lead somebody astray"),
        ]:
            service: Any = FactoryService.__new__(FactoryService)
            install_completion(self, service)
            service.completions.words_path.write_text(f"{original}\n{expected}\n", encoding="utf-8")
            session = install_source(service)
            service.sessions.update_session(
                session["id"],
                deck_name="English",
                model_name="Basic",
                field_mapping={
                    "englishField": "en_word",
                    "translationField": "pl_translation",
                    "audioField": "audio_en",
                },
            )
            service.diki = DikiApi(
                Mock(fetch_html=Mock(return_value=document), fetch_audio=Mock(return_value=MP3))
            )
            service.notes = Mock(get_note_id=Mock(return_value=None))
            service.anki = Mock(last_error=None)
            service.anki.find_notes_by_field.return_value = []
            service.anki.notes_info.return_value = []
            service.anki.invoke.return_value = "Test"
            service.anki.model_schema.return_value = {
                "fields": ["en_word", "pl_translation", "audio_en"]
            }
            service.anki.add_note.return_value = 99
            service.anki.get_note_cards.return_value = [{"cardId": 1, "deckName": "English"}]
            service.anki.get_note.side_effect = lambda note_id, service=service: {
                "noteId": note_id,
                "modelName": "Basic",
                "tags": [],
                "fields": {
                    key: {"value": value}
                    for key, value in service.anki.add_note.call_args.args[2].items()
                },
            }
            lookup = service.lookup_current(session["id"], entry_id=session["current"]["id"])
            self.assertEqual(lookup["word"], expected)
            self.assertEqual(lookup["sourceWord"], original)
            draft = service.session(session["id"])["draft"]
            draft["groups"][0][0]["selected"] = True
            draft["word"] = "incorrect client spelling"
            service.update_current_draft(session["id"], draft, entry_id=session["current"]["id"])
            self.assertEqual(service.preview_current(session["id"])["fields"]["en_word"], expected)
            service.commit_current(
                session["id"], "create", [], None, entry_id=session["current"]["id"]
            )
            self.assertEqual(service.anki.add_note.call_args.args[2]["en_word"], expected)
            self.assertEqual(service.completions.words_path.read_text(), expected + "\n")
            with service.completions.connect() as db:
                self.assertEqual(
                    db.execute("SELECT en_word FROM note_index").fetchone()[0], expected
                )

    def test_index_hit_and_anki_candidates_do_not_conflate_case_distinct_entries(self):
        service: Any = FactoryService.__new__(FactoryService)
        service.notes = Mock(get_note_id=Mock(return_value=1))
        service.anki = Mock(last_error=None)
        service.anki.find_notes_by_field.return_value = [1, 2]
        notes = [
            {"noteId": 1, "fields": {"en_word": {"value": "polish"}}},
            {"noteId": 2, "fields": {"en_word": {"value": "Polish"}}},
        ]
        service.anki.notes_info.return_value = notes
        session = {"fieldMapping": {"englishField": "en_word"}}
        self.assertEqual(service._find_existing_note_id("Polish", session, case_sensitive=True), 2)
        service.anki.notes_info.return_value = notes[:1]
        self.assertIsNone(service._find_existing_note_id("Polish", session, case_sensitive=True))
        self.assertEqual(service._find_existing_note_id("Polish", session), 1)

    def test_case_sensitive_refresh_rejects_a_note_from_the_other_entry(self):
        service: Any = FactoryService.__new__(FactoryService)
        install_completion(self, service)
        service.diki = Mock()
        service.anki = Mock(last_error=None)
        service.anki.invoke.return_value = "Test"
        service.anki.get_note.return_value = {
            "modelName": "Basic",
            "fields": {"en_word": {"value": "polish"}},
            "tags": [],
        }
        service.anki.get_note_cards.return_value = [{"cardId": 1, "deckName": "English"}]
        with self.assertRaisesRegex(ServiceError, "different English word"):
            service._perform_commit(
                {"modelName": "Basic", "fieldMapping": {"englishField": "en_word"}},
                {"en_word": "Polish"},
                [],
                [],
                "update",
                1,
                "Polish",
                None,
                None,
                case_sensitive=True,
            )
        service.anki.update_note_fields.assert_not_called()

    def test_media_filenames_do_not_collide_on_case_insensitive_filesystems(self):
        self.assertNotEqual(
            FactoryService._audio_filename("Polish").lower(),
            FactoryService._audio_filename("polish").lower(),
        )
