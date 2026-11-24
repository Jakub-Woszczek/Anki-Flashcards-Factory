"""Progress polling stays responsive and never duplicates an in-flight cache scan."""

import os
import tempfile
import threading
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from backend.offline_coverage import OfflineCoverage
from external_apis.diki_lists import WordList, coverage
from external_apis.diki_resources import DikiResources
from tests.test_diki_resources import HTML, MP3


class TestOfflineCoverage(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        environment = patch.dict(os.environ, {"ANKI_FACTORY_DATA_DIR": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        self.resources = DikiResources(
            self.root / "diki_cache",
            offline=True,
            get=Mock(side_effect=AssertionError("No Diki requests")),
        )
        self.addCleanup(self.resources.close)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Coverage worker did not reach the expected state")

    def finish(self, worker):
        worker.close()
        if worker.thread is not None:
            worker.thread.join(timeout=8)
            self.assertFalse(worker.thread.is_alive())

    def test_real_scan_reports_resource_recording_and_word_totals(self):
        self.resources._save("take", "html", HTML, 200, "fixture", True)
        self.resources._save(
            "take", "audio", MP3, 200, "https://www.diki.pl/images-common/en/mp3/take.mp3"
        )
        progress = Mock()
        lists = [WordList("main", ["take", "missing"], 2), WordList("book", ["take"], 1)]
        result = coverage(self.resources, lists, progress=progress)
        self.assertEqual(result["lists"][0]["total"], 2)
        self.assertEqual(result["lists"][0]["ready"], 1)
        events = [call.args for call in progress.call_args_list]
        for stage, total in [
            ("Checking cached resources", 2),
            ("Checking recording provenance", 1),
            ("Calculating list coverage", 3),
        ]:
            self.assertEqual(
                [event[1:] for event in events if event[0] == stage],
                [(done, total) for done in range(total + 1)],
            )

    def test_empty_scan_reports_zero_totals_without_fake_work(self):
        progress = Mock()
        result = coverage(self.resources, [], progress=progress)
        self.assertEqual(result["lists"], [])
        self.assertEqual(
            [call.args for call in progress.call_args_list],
            [
                ("Discovering vocabulary lists", 0, None),
                ("Checking cached resources", 0, 0),
                ("Checking recording provenance", 0, 0),
                ("Calculating list coverage", 0, 0),
            ],
        )

    def test_progress_reads_are_nonblocking_and_coalesce_until_the_scan_finishes(self):
        entered, release = threading.Event(), threading.Event()

        def slow_scan(resources, *, progress):
            progress("Checking cached resources", 1, 3)
            entered.set()
            release.wait(5)
            progress("Checking cached resources", 3, 3)
            return {"lists": [{"name": "finished"}]}

        with patch("backend.offline_coverage.coverage", side_effect=slow_scan) as scan:
            worker = OfflineCoverage(self.resources.root)
            worker.start()
            worker.start()
            try:
                self.assertTrue(entered.wait(3))
                before = time.monotonic()
                for _ in range(20):
                    state = worker.status()
                    self.assertTrue(state["loading"])
                    self.assertFalse(state["listsAvailable"])
                    self.assertEqual(state["progress"]["processed"], 1)
                    self.assertEqual(state["progress"]["total"], 3)
                self.assertLess(time.monotonic() - before, 0.2)
                self.assertEqual(scan.call_count, 1)
                release.set()
                self.wait_for(lambda: not worker.status()["loading"])
                self.assertTrue(worker.status()["listsAvailable"])
                self.assertEqual(worker.status()["lists"], [{"name": "finished"}])
                for _ in range(20):
                    worker.status()
                self.assertEqual(scan.call_count, 1)
            finally:
                release.set()
                self.finish(worker)

    def test_refresh_failure_keeps_previous_statistics_and_stops_loading(self):
        entered, release = threading.Event(), threading.Event()
        calls = []

        def scan(resources, *, progress):
            calls.append(resources)
            if len(calls) == 1:
                return {"lists": [{"name": "saved"}]}
            progress("Checking cached resources", 1, 2)
            entered.set()
            release.wait(5)
            raise OSError("Unreadable cache index")

        with patch("backend.offline_coverage.coverage", side_effect=scan):
            worker = OfflineCoverage(self.resources.root)
            worker.start()
            try:
                self.wait_for(lambda: worker.status()["listsAvailable"])
                with worker.lock:
                    worker._next_refresh = 0
                worker.status()
                self.assertTrue(entered.wait(3))
                state = worker.status()
                self.assertTrue(state["loading"])
                self.assertEqual(state["lists"], [{"name": "saved"}])
                release.set()
                self.wait_for(lambda: not worker.status()["loading"])
                self.assertEqual(worker.status()["coverageError"], "Unreadable cache index")
                self.assertEqual(worker.status()["lists"], [{"name": "saved"}])
                self.assertEqual(len(calls), 2)
            finally:
                release.set()
                self.finish(worker)

    def test_shutdown_cancels_progress_without_waiting_for_the_scan(self):
        entered, release = threading.Event(), threading.Event()

        def scan(resources, *, progress):
            entered.set()
            release.wait(5)
            progress("Checking cached resources", 1, 2)
            raise AssertionError("Cancelled scan must not continue")

        with patch("backend.offline_coverage.coverage", side_effect=scan):
            worker = OfflineCoverage(self.resources.root)
            worker.start()
            try:
                self.assertTrue(entered.wait(3))
                before = time.monotonic()
                worker.close()
                self.assertLess(time.monotonic() - before, 0.2)
            finally:
                release.set()
                self.finish(worker)
            self.assertFalse(worker.status()["listsAvailable"])
