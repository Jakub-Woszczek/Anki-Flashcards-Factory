"""Saved-first coverage, collection reconciliation, and review without live integrations."""

import copy
import json
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from backend.existing_note_coverage import ExistingNoteCoverage, html_coverage
from backend.note_contracts import NOTE_TYPES
from backend.note_index import NotesDatabase
from backend.settings import diki_coverage_inventory
from external_apis.diki_inventory import export_inventory, load_inventory, save_inventory
from external_apis.diki_resources import DikiResources
from tests.test_diki_page import fixture


class InventoryAnki:
    def __init__(self, values, profile="Main"):
        self.values = values
        self.profile = profile
        self.last_error = None
        self.calls = []

    def invoke(self, action, **params):
        self.calls.append((action, params))
        if action == "getActiveProfile":
            return self.profile
        if action == "findNotes":
            model = json.loads(params["query"][5:])
            if model not in NOTE_TYPES:
                raise AssertionError("Unexpected inventory scope")
            return [note_id for note_id, (name, _) in self.values.items() if name == model]
        if action == "notesInfo":
            return [
                {
                    "noteId": note_id,
                    "modelName": self.values[note_id][0],
                    "fields": {"en_word": {"value": self.values[note_id][1]}},
                }
                for note_id in params["notes"]
            ]
        raise AssertionError(f"Unexpected Anki mutation/request: {action}")


class CoverageFixture(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        environment = patch.dict(os.environ, {"ANKI_FACTORY_DATA_DIR": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        self.get = Mock(side_effect=AssertionError("Coverage must never request Diki"))
        self.resources = DikiResources(self.root / "diki_cache", get=self.get, offline=True)
        self.addCleanup(self.resources.close)
        self.notes = NotesDatabase()

    def inventory(self, values, *, profile="Main"):
        return export_inventory(InventoryAnki(values, profile))

    def cache(self, word, document, *, exact=False):
        self.resources._save(word, "html", document.encode(), 200, "fixture", exact)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Coverage worker did not reach the expected state")

    def worker(self, api, **kwargs):
        worker = ExistingNoteCoverage(self.resources.root, lambda: api, self.notes, **kwargs)
        self.addCleanup(self.finish, worker)
        worker.start()
        return worker

    def finish(self, worker):
        worker.close()
        if worker.thread is not None:
            worker.thread.join(timeout=8)
            self.assertFalse(worker.thread.is_alive())


class TestStrictHtmlCoverage(CoverageFixture):
    def test_every_category_counts_notes_and_only_entries_meet_goal_without_audio(self):
        words = ["take", "briben", "prologs", "divert off", "absent", "unknown", "missing"]
        values = {index: (NOTE_TYPES[0], word) for index, word in enumerate(words, 1)}
        values[8] = (NOTE_TYPES[1], "<b>bad English</b>")
        inventory = self.inventory(values)
        for word, name in zip(
            words[:5], ["entries", "suggestions", "related", "collocation", "reverse"], strict=True
        ):
            self.cache(word, fixture(name))
        self.cache("unknown", "<p>Changed dictionary layout</p>", exact=True)
        report = html_coverage(inventory, self.resources, {})
        self.assertEqual((report["total"], report["entries"], report["percent"]), (8, 1, 12.5))
        counts = {category["key"]: category["count"] for category in report["categories"]}
        self.assertEqual(counts.pop("unusable"), 0)
        self.assertTrue(all(count == 1 for count in counts.values()))
        self.assertEqual(sum(category["percent"] for category in report["categories"]), 100)
        self.assertEqual({note["noteId"] for note in report["review"]}, set(range(2, 9)))
        invalid = report["review"][-1]
        self.assertEqual(invalid["word"], "<b>bad English</b>")
        self.assertEqual(invalid["category"], "unprocessable")
        self.assertTrue(invalid["reason"])
        self.get.assert_not_called()
        self.assertFalse(any(self.resources.root.glob("audio/*.mp3")))

    def test_counts_are_not_based_on_stale_exact_flags_or_headword_order(self):
        document = fixture("entries").replace("take", "different")
        self.cache("take", document, exact=False)
        inventory = self.inventory({1: (NOTE_TYPES[0], "take")})
        report = html_coverage(inventory, self.resources, {})
        self.assertEqual(report["percent"], 100)
        self.assertEqual(report["review"], [])

    def test_corrupt_deleted_and_replaced_files_are_rechecked_without_overwriting_them(self):
        inventory = self.inventory({1: (NOTE_TYPES[0], "take")})
        self.cache("take", fixture("entries"))
        memo = {}
        self.assertEqual(html_coverage(inventory, self.resources, memo)["entries"], 1)
        self.resources.path("take", "html").write_text("corrupted bytes")
        self.assertEqual(
            html_coverage(inventory, self.resources, memo)["review"][0]["category"], "unusable"
        )
        self.assertEqual(self.resources.path("take", "html").read_text(), "corrupted bytes")
        self.assertEqual(memo, {})
        self.cache("take", fixture("suggestions"))
        self.assertEqual(
            html_coverage(inventory, self.resources, memo)["review"][0]["category"], "suggestions"
        )
        self.resources.path("take", "html").unlink()
        self.assertEqual(
            html_coverage(inventory, self.resources, memo)["review"][0]["category"], "missing"
        )
        self.get.assert_not_called()

    def test_missing_and_unusable_html_have_separate_counts_and_denominator(self):
        values = {
            index: (NOTE_TYPES[0], word)
            for index, word in enumerate(
                ["take", "never downloaded", "corrupt", "unreadable", "unindexed"], 1
            )
        }
        self.cache("take", fixture("entries"))
        self.cache("corrupt", fixture("entries"))
        self.resources.path("corrupt", "html").write_bytes(b"broken")
        self.cache("unreadable", fixture("entries"))
        self.resources.path("unindexed", "html").write_text(fixture("entries"))
        read_bytes = Path.read_bytes
        unreadable = self.resources.path("unreadable", "html")

        def read(path):
            if path == unreadable:
                raise PermissionError("Cannot read cached HTML")
            return read_bytes(path)

        with patch.object(Path, "read_bytes", read):
            report = html_coverage(self.inventory(values), self.resources, {})
        self.assertEqual((report["total"], report["percent"]), (5, 20))
        categories = {category["key"]: category for category in report["categories"]}
        self.assertEqual(categories["missing"]["count"], 1)
        self.assertEqual(categories["unusable"]["count"], 3)
        self.assertEqual(categories["missing"]["percent"], 20)
        self.assertEqual(categories["unusable"]["percent"], 60)
        self.assertEqual(
            {note["word"]: note["category"] for note in report["review"]},
            {
                "never downloaded": "missing",
                "corrupt": "unusable",
                "unreadable": "unusable",
                "unindexed": "unusable",
            },
        )
        self.get.assert_not_called()

    def test_meaningful_case_and_zero_notes_are_preserved(self):
        self.cache("Polish", fixture("entries"))
        self.cache("polish", fixture("suggestions"))
        report = html_coverage(
            self.inventory({1: (NOTE_TYPES[0], "Polish"), 2: (NOTE_TYPES[0], "polish")}),
            self.resources,
            {},
        )
        self.assertEqual(report["percent"], 50)
        self.assertEqual(report["review"][0]["word"], "polish")
        empty = html_coverage(self.inventory({}), self.resources, {})
        self.assertTrue(empty["available"])
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["percent"], 0)


class TestStartupCoverage(CoverageFixture):
    def test_saved_stats_publish_before_anki_then_changes_refresh_inventory_and_stats(self):
        original = self.inventory({1: (NOTE_TYPES[0], "take"), 2: (NOTE_TYPES[0], "removed")})
        save_inventory(original)
        self.cache("take", fixture("entries"))
        api = InventoryAnki({1: (NOTE_TYPES[0], "changed"), 3: (NOTE_TYPES[1], "new")})
        entered, release = threading.Event(), threading.Event()
        invoke = api.invoke

        def blocked(action, **params):
            if not entered.is_set():
                entered.set()
                release.wait(5)
            return invoke(action, **params)

        api.invoke = blocked
        notified = Mock()
        worker = self.worker(api, on_reconciled=notified)
        try:
            self.assertTrue(entered.wait(3))
            initial = worker.status()
            self.assertEqual(initial["reconciliation"], "checking")
            self.assertEqual((initial["total"], initial["entries"]), (2, 1))
            self.assertEqual(load_inventory()["notes"], original["notes"])
        finally:
            release.set()
        self.wait_for(lambda: worker.status()["reconciliation"] == "complete")
        final = worker.status()
        self.assertEqual(final["changes"], {"added": 1, "changed": 1, "removed": 1})
        self.assertEqual(final["entries"], 0)
        self.assertEqual({note["noteId"] for note in final["review"]}, {1, 3})
        self.assertEqual(load_inventory()["words"], ["changed", "new"])
        self.wait_for(lambda: notified.call_count == 1)
        self.get.assert_not_called()

    def test_polling_refreshes_html_without_scanning_anki_again(self):
        api = InventoryAnki({1: (NOTE_TYPES[0], "take")})
        worker = self.worker(api, refresh_interval=0)
        self.wait_for(lambda: worker.status()["reconciliation"] == "complete")
        self.assertEqual(worker.status()["entries"], 0)
        calls = list(api.calls)
        self.cache("take", fixture("entries"))
        self.wait_for(lambda: worker.status()["entries"] == 1)
        self.assertEqual(api.calls, calls)
        self.get.assert_not_called()

    def test_classification_reports_exact_note_progress(self):
        inventory = self.inventory(
            {
                1: (NOTE_TYPES[0], "take"),
                2: (NOTE_TYPES[0], "missing"),
                3: (NOTE_TYPES[0], "<b>invalid</b>"),
            }
        )
        self.cache("take", fixture("entries"))
        progress = Mock()
        report = html_coverage(inventory, self.resources, {}, progress=progress)
        self.assertEqual(report["total"], 3)
        self.assertEqual(
            [call.args for call in progress.call_args_list],
            [("Classifying existing-note HTML", done, 3) for done in range(4)],
        )
        empty_progress = Mock()
        html_coverage(self.inventory({}), self.resources, {}, progress=empty_progress)
        empty_progress.assert_called_once_with("Classifying existing-note HTML", 0, 0)

    def test_anki_unavailable_keeps_saved_stats_and_exposes_actual_error(self):
        original = self.inventory({1: (NOTE_TYPES[0], "take")})
        save_inventory(original)
        self.cache("take", fixture("entries"))
        api = Mock(last_error="Open Anki first")
        api.invoke.return_value = None
        worker = self.worker(api)
        self.wait_for(lambda: worker.status()["reconciliation"] == "error")
        state = worker.status()
        self.assertEqual(state["entries"], 1)
        self.assertEqual(state["reconciliationError"], "Open Anki first")
        self.assertEqual(load_inventory()["createdAt"], original["createdAt"])

    def test_profile_switch_and_partial_responses_cannot_replace_saved_inventory(self):
        original = self.inventory({1: (NOTE_TYPES[0], "take")})
        save_inventory(original)
        for mode in ("other-profile", "switch-during-export", "partial"):
            with self.subTest(mode=mode):
                api = InventoryAnki({1: (NOTE_TYPES[0], "take")})
                invoke = api.invoke
                profile_calls = []

                def broken(action, mode=mode, profile_calls=profile_calls, invoke=invoke, **params):
                    if action == "getActiveProfile":
                        profile_calls.append(action)
                        if mode == "other-profile" or (
                            mode == "switch-during-export" and len(profile_calls) > 1
                        ):
                            return "Other"
                    if mode == "partial" and action == "notesInfo":
                        return []
                    return invoke(action, **params)

                api.invoke = broken
                worker = self.worker(api)
                self.wait_for(lambda worker=worker: worker.status()["reconciliation"] == "error")
                self.finish(worker)
                self.assertEqual(load_inventory()["createdAt"], original["createdAt"])

    def test_missing_or_legacy_export_is_created_or_upgraded_with_note_ids(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                diki_coverage_inventory().unlink(missing_ok=True)
                if legacy:
                    save_inventory({"version": 1, "words": ["take"], "invalidCount": 0})
                worker = self.worker(InventoryAnki({1: (NOTE_TYPES[0], "take")}))
                self.wait_for(lambda worker=worker: worker.status()["reconciliation"] == "complete")
                self.finish(worker)
                self.assertEqual(load_inventory()["version"], 2)
                self.assertEqual(worker.status()["review"][0]["noteId"], 1)

    def test_shutdown_does_not_wait_for_anki_or_save_a_late_export(self):
        original = self.inventory({1: (NOTE_TYPES[0], "take")})
        save_inventory(original)
        entered, release = threading.Event(), threading.Event()
        api = InventoryAnki({1: (NOTE_TYPES[0], "changed")})
        invoke = api.invoke

        def blocked(action, **params):
            entered.set()
            release.wait(5)
            return invoke(action, **params)

        api.invoke = blocked
        worker = self.worker(api)
        try:
            self.assertTrue(entered.wait(3))
            before = time.monotonic()
            worker.close()
            self.assertLess(time.monotonic() - before, 0.2)
        finally:
            release.set()
            self.finish(worker)
        self.assertEqual(load_inventory()["createdAt"], original["createdAt"])


class TestInventoryConsistency(CoverageFixture):
    def test_index_check_reports_missing_changed_and_outside_entries_without_repairs(self):
        with self.notes._connect() as connection:
            connection.executemany(
                "INSERT INTO note_index VALUES (?,?,?)",
                [
                    ("take", "take", 1),
                    ("take alias", "take alias", 1),
                    ("changed", "old spelling", 2),
                    ("wrong id", "wrong id", 99),
                    ("outside", "outside", 100),
                ],
            )
        inventory = self.inventory(
            {
                1: (NOTE_TYPES[0], "take"),
                2: (NOTE_TYPES[0], "new spelling"),
                3: (NOTE_TYPES[0], "wrong id"),
                4: (NOTE_TYPES[0], "missing"),
            }
        )
        with self.notes._connect() as connection:
            before = list(connection.execute("SELECT * FROM note_index"))
        issues = self.notes.inventory_discrepancies(inventory)
        self.assertEqual({issue["noteId"] for issue in issues}, {1, 2, 3, 4, 99, 100})
        self.assertEqual(
            next(issue for issue in issues if issue["noteId"] == 1)["indexedWord"], "take alias"
        )
        self.assertEqual(
            next(issue for issue in issues if issue["noteId"] == 3)["indexedNoteId"], 99
        )
        with self.notes._connect() as connection:
            self.assertEqual(list(connection.execute("SELECT * FROM note_index")), before)

    def test_invalid_inventory_records_fail_before_being_used_for_coverage(self):
        original = self.inventory({1: (NOTE_TYPES[0], "take")})
        for field, value in [
            ("notes", []),
            ("words", ["different"]),
            ("checked", 20),
            ("invalidCount", 1),
        ]:
            broken = copy.deepcopy(original)
            broken[field] = value
            save_inventory(broken)
            with self.assertRaises(ValueError):
                load_inventory()

    def test_index_failure_does_not_hide_valid_note_coverage(self):
        with patch.object(
            self.notes,
            "inventory_discrepancies",
            side_effect=sqlite3.OperationalError("index unavailable"),
        ):
            worker = self.worker(InventoryAnki({1: (NOTE_TYPES[0], "take")}))
            self.wait_for(lambda: worker.status()["reconciliation"] == "complete")
            self.finish(worker)
        self.assertEqual(worker.status()["indexError"], "index unavailable")
        self.assertTrue(worker.status()["available"])
