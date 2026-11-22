import json
import tempfile
from pathlib import Path
from typing import Any
from unittest import TestCase
from unittest.mock import Mock

from bs4 import BeautifulSoup

from backend.services import FactoryService
from external_apis.diki_api import DikiApi, resolve_lookup
from external_apis.diki_page import inspect_page
from external_apis.diki_resources import Blocked, DikiResources, ResourceError
from tests.completion_helpers import install_completion, install_source
from tests.test_diki_headwords import entry
from tests.test_diki_resources import response

CASES = Path(__file__).parent / "diki_cases"


def fixture(name):
    return (CASES / f"page-{name}.html").read_text(encoding="utf-8")


class TestPageRecognition(TestCase):
    def test_owner_supplied_result_types_and_collocation_content_is_not_a_meaning(self):
        for query, name, kind in [
            ("take", "entries", "entries"),
            ("briben", "suggestions", "suggestions"),
            ("aoifnesfl", "not-found", "not_found"),
            ("Divert off", "collocation", "collocation"),
            ("torta", "reverse", "not_found"),
        ]:
            with self.subTest(query=query):
                result = resolve_lookup(fixture(name), query)
                assert result.page is not None
                self.assertEqual(result.page.kind, kind)
                self.assertEqual(bool(result.meanings), name == "entries")
        result = resolve_lookup(fixture("entries"), "take")
        assert result.page is not None
        self.assertEqual(result.translations, [["brać", "zabierać"]])
        self.assertFalse(result.page.has_collocations)  # Related links are not full results.

    def test_entries_dominate_collocations_and_both_dictionary_directions(self):
        document = fixture("reverse")
        # Controlled mixed-direction fragment models cylinder's independent sections.
        soup = BeautifulSoup(document, "html.parser")
        scope = soup.select_one(".dikiContainer")
        assert scope is not None
        for extra in (fixture("collocation"), fixture("entries")):
            extra_scope = BeautifulSoup(extra, "html.parser").select_one(".dikiContainer")
            assert extra_scope is not None
            for child in list(extra_scope.contents):
                scope.append(child)
        result = resolve_lookup(str(soup), "take")
        assert result.page is not None
        self.assertEqual(result.page.kind, "entries")
        self.assertTrue(result.page.has_reverse_entries)
        self.assertTrue(result.page.has_collocations)
        self.assertEqual(result.translations, [["brać", "zabierać"]])

    def test_related_rows_offer_first_complete_headword_not_aliases_or_translations(self):
        result = resolve_lookup(fixture("related"), "prologs")
        assert result.page is not None
        self.assertEqual(result.page.kind, "related")
        self.assertEqual(result.related_entries, ["prologue", "prologising", "prologize"])
        self.assertEqual(result.suggestions, [])
        self.assertEqual(result.entry_choices, [])
        self.assertIsNone(result.word)
        combined = fixture("related").replace(
            '<div class="dikiContainer">',
            '<div class="dikiContainer"><div class="dictionarySuggestions"><a>prologue</a></div>',
        )
        preferred = resolve_lookup(combined, "prologs")
        self.assertEqual(preferred.suggestions, ["prologue"])
        self.assertEqual(preferred.related_entries, [])

    def test_unique_entry_uses_first_genuine_alternative_even_when_collocation_matches_query(self):
        document = entry("give somebody a hand", "pomóc komuś").replace(
            '<span class="hw">give somebody a hand</span>',
            '<span class="hw">give somebody a hand</span><span class="hw">lend somebody a hand</span>',
        )
        collocation = (
            fixture("collocation")
            .replace("Divert off", "lend a hand")
            .replace("divert off", "lend a hand")
        )
        mixed = collocation.replace(
            '<div class="dikiContainer">', '<div class="dikiContainer">' + document
        )
        result = resolve_lookup(mixed, "lend a hand")
        assert result.page is not None
        self.assertEqual(result.page.kind, "entries")
        self.assertEqual(result.word, "give somebody a hand")
        self.assertEqual(result.translations, [["pomóc komuś"]])
        self.assertEqual(result.entry_choices, [])
        self.assertEqual(
            resolve_lookup(document, "lend somebody a hand").word, "lend somebody a hand"
        )

    def test_word_by_word_is_negative_evidence_not_related_entry_choices(self):
        document = """<p>Poniżej prezentujemy tłumaczenia poszczególnych wyrazów.</p>
        <ul class="wordByWordTranslation"><li><div class="dictionaryEntity"><div class="fentry">
        <span class="fentrymain"><span class="hw">have</span></span> = mieć
        </div></div></li></ul>"""
        result = resolve_lookup(document, "have nowhere")
        assert result.page is not None
        self.assertEqual(result.page.kind, "not_found")
        self.assertTrue(result.page.word_by_word)
        self.assertEqual(result.related_entries, [])
        preferred = resolve_lookup(
            '<div class="dictionarySuggestions"><a>nowhere</a></div>' + document, "nowher"
        )
        assert preferred.page is not None
        self.assertEqual(preferred.page.kind, "suggestions")

    def test_auto_translation_is_optional_and_empty_shells_are_unknown(self):
        soup = BeautifulSoup(fixture("collocation"), "html.parser")
        automatic = soup.select_one(".automaticCollocationTranslation")
        assert automatic is not None
        automatic.decompose()
        self.assertEqual(inspect_page(soup).kind, "collocation")
        for document in [
            '<div class="dictionaryEntity"><div class="hws"><span class="hw">new</span></div></div>',
            '<div class="dictionarySuggestions"></div>',
            '<div class="collocationSearchResults"><div class="dictionaryCollocationUnits"></div></div>',
            "<footer>Nie znaleziono problemów w witrynie</footer>",
        ]:
            self.assertEqual(inspect_page(BeautifulSoup(document, "html.parser")).kind, "unknown")


class TestRecognitionResources(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.get = Mock(return_value=response(fixture("collocation").encode()))
        self.resources = DikiResources(self.root / "cache", get=self.get, interval=0, jitter=0)
        self.addCleanup(self.resources.close)

    def test_collocation_and_reverse_results_are_cached_without_pausing(self):
        for name, query in [("collocation", "Divert off"), ("reverse", "torta")]:
            self.get.return_value = response(fixture(name).encode())
            result = DikiApi(self.resources).lookup(query)
            self.assertFalse(result.meanings)
            row = self.resources.metadata(query, "html")
            assert row is not None
            self.assertEqual((row["state"], row["exact_match"]), ("ready", 0))
            self.assertEqual(self.resources.setting("cooldown_until", 0), 0)
        self.resources.offline = True
        self.get.reset_mock()
        result = DikiApi(self.resources).lookup("Divert off")
        assert result.page is not None
        self.assertEqual(result.page.kind, "collocation")
        self.get.assert_not_called()

    def test_unknown_network_and_cached_pages_leave_durable_bounded_diagnostics(self):
        body = b"<title>Changed layout</title><script>secret-browser-token</script><div>new template</div>"
        self.get.return_value = response(body)
        with self.assertRaises(ResourceError):
            self.resources.fetch_html("unusual")
        self.resources._save("cached", "html", body, 200, "fixture", False)
        DikiApi(self.resources).lookup("cached")
        records = [
            json.loads(line) for line in self.resources.diagnostics_path.read_text().splitlines()
        ]
        self.assertEqual([r["origin"] for r in records], ["network", "cache"])
        self.assertEqual([r["query"] for r in records], ["unusual", "cached"])
        self.assertEqual(records[0]["sha256"], records[1]["sha256"])
        self.assertNotIn("secret-browser-token", json.dumps(records))
        self.assertIn("markers", records[0])

    def test_explicit_challenge_header_still_wins_over_collocation_content(self):
        self.get.return_value = response(
            fixture("collocation").encode(), headers={"CF-Mitigated": "challenge"}
        )
        with self.assertRaises(Blocked):
            self.resources.fetch_html("Divert off")
        self.assertFalse(self.resources.path("Divert off", "html").exists())

    def test_ambiguous_choice_reuses_original_html_and_preserves_only_chosen_translations(self):
        document = entry("take issue with somebody", "nie zgadzać się z kimś") + entry(
            "take issue with something", "nie zgadzać się z czymś"
        )
        self.get.return_value = response(document.encode())
        api = DikiApi(self.resources)
        result = api.lookup("take issue with sb")
        self.assertEqual(
            result.entry_choices, ["take issue with somebody", "take issue with something"]
        )
        self.assertEqual(result.suggestions, [])
        self.resources.offline = True
        selected = api.lookup("take issue with sb", headword="take issue with somebody")
        self.assertEqual(selected.translations, [["nie zgadzać się z kimś"]])
        self.assertEqual(api.lookup("take issue with somebody").translations, selected.translations)
        self.assertEqual(self.get.call_count, 1)
        with self.assertRaisesRegex(ResourceError, "not an English"):
            api.lookup("take issue with sb", headword="invented")

    def test_backend_choice_keeps_source_occurrence_and_exposes_separate_choice_types(self):
        service: Any = FactoryService.__new__(FactoryService)
        install_completion(self, service)
        service.completions.words_path.write_text("take issue with sb\nnext\n", encoding="utf-8")
        session = install_source(service)
        service.diki = DikiApi(self.resources)
        service.notes = Mock(get_note_id=Mock(return_value=None))
        service.anki = Mock(last_error=None)
        service.anki.find_notes_by_field.return_value = []
        service.anki.notes_info.return_value = []
        self.get.return_value = response(
            (
                entry("take issue with somebody", "nie zgadzać się z kimś")
                + entry("take issue with something", "nie zgadzać się z czymś")
            ).encode()
        )
        first = service.lookup_current(session["id"], entry_id=session["current"]["id"])
        self.assertEqual(first["pageKind"], "entries")
        self.assertFalse(first["exactMatch"])
        selected = service.lookup_current(
            session["id"],
            first["lookupQuery"],
            entry_id=session["current"]["id"],
            headword=first["entryChoices"][0],
        )
        self.assertEqual(selected["sourceWord"], "take issue with sb")
        self.assertEqual(selected["resolvedWord"], "take issue with somebody")
        self.assertEqual(self.get.call_count, 1)
        self.assertEqual(service.completions.words_path.read_text(), "take issue with sb\nnext\n")
        self.assertEqual(
            service.session(session["id"])["draft"]["lookupQuery"], "take issue with sb"
        )
