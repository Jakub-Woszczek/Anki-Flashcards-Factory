"""Offline scheduling contracts using the actual remote API and temporary data."""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import requests

from backend.remote_preparation import RemotePreparation
from external_apis.diki_inventory import (
    export_inventory,
    import_inventory,
    load_inventory,
    save_inventory,
)
from external_apis.diki_lists import discover_lists
from external_apis.diki_remote import RemoteDownloads, RemoteError, RemoteStopped
from external_apis.diki_resources import DikiResources, file_lock
from tests import test_diki_remote as fixtures
from tests.test_diki_resources import HTML, MP3, SUGGESTIONS, response


class RemoteFixture(TestCase):
    root: Path
    service: Any
    local: Any
    client: RemoteDownloads
    adapter: fixtures.ApiAdapter
    get: Mock
    clock: fixtures.Clock
    setUp = fixtures.TestRemoteDownloads.setUp
    make_service = fixtures.TestRemoteDownloads.make_service
    ready = fixtures.TestRemoteDownloads.ready


class TestScheduledRemote(RemoteFixture):
    def word_responses(self, url, **kwargs):
        if "/mp3/" in url:
            return response(MP3)
        word = parse_qs(urlsplit(url).query)["q"][0]
        return response(HTML.replace(b"take", word.encode()))

    def test_priority_preempts_an_existing_coverage_backlog(self):
        self.service.config.batch_words = 1
        self.get.side_effect = self.word_responses
        self.service.submit([{"word": "backlog", "need_audio": False, "priority": "coverage"}])
        self.client.submit(["take"], self.local, priority="buffer")
        self.service.run_cycle()
        self.assertIn("q=take", self.get.call_args_list[0].args[0])
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.service.status()["jobs"], {"queued": 1, "ready": 1})

    def test_duplicate_goals_in_one_submission_keep_the_stronger_requirement(self):
        result = self.service.submit(
            [
                {"word": "take", "need_audio": False, "priority": "coverage"},
                {"word": "take", "need_audio": True, "priority": "buffer"},
            ]
        )
        self.assertEqual(result["queued"], 1)
        self.service.run_cycle()
        self.client.pull(self.local)
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_coverage_reuses_local_html_and_never_requests_audio(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.get.side_effect = self.word_responses
        result = self.client.submit(
            ["take", "backlog"], self.local, html_only=True, priority="coverage"
        )
        self.assertEqual((result["queued"], result["alreadyCached"]), (1, 1))
        self.assertFalse(self.adapter.job_bodies[0]["items"][0]["need_audio"])
        self.service.run_cycle()
        self.client.pull(self.local)
        self.assertEqual(self.get.call_count, 1)
        self.assertIsNone(self.local._cached("backlog", "audio"))

    def test_coverage_reuses_a_safe_capitalization_alias_locally(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        result = self.client.submit(["Take"], self.local, html_only=True, priority="coverage")
        self.assertEqual(result["alreadyCached"], 1)
        self.assertEqual(self.local._cached("Take", "html"), HTML)
        self.assertEqual(self.adapter.calls, [])
        self.get.assert_not_called()

    def test_queued_and_running_coverage_can_be_promoted_without_repeating_html(self):
        for running in (False, True):
            with self.subTest(running=running):
                word = "take" if not running else "other"
                self.service.submit([{"word": word, "need_audio": False, "priority": "coverage"}])

                def fetch(url, running=running, word=word, **kwargs):
                    if "/mp3/" not in url and running:
                        self.service.submit([{"word": word, "need_audio": True}])
                    return self.word_responses(url, **kwargs)

                self.get.side_effect = fetch
                if not running:
                    self.service.submit([{"word": word}])
                before = self.get.call_count
                self.service.run_cycle()
                self.client.pull(self.local)
                self.assertEqual(self.get.call_count - before, 2)
                self.assertIsNotNone(self.local._cached(word, "audio"))

    def test_batched_html_promotion_keeps_manifest_and_old_ack_isolation(self):
        self.ready(need_audio=False)
        envelope = self.service.next_transfer()
        old_id = envelope["manifest"]["id"]
        self.assertEqual(self.service.submit([{"word": "take"}])["queued"], 1)
        self.assertEqual(self.service.next_transfer(), envelope)
        self.client.pull(self.local)
        self.assertEqual(self.service.status()["jobs"], {"queued": 1})
        self.service.acknowledge(old_id, envelope["digest"])
        self.assertIsNotNone(self.service.resources._cached("take", "html"))
        self.service.run_cycle()
        self.client.pull(self.local)
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_delivered_html_can_gain_audio_without_redownload_flags(self):
        self.ready(need_audio=False)
        self.client.pull(self.local)
        self.assertEqual(
            self.client.submit(["take"], self.local, priority="buffer")["audioOnly"], 1
        )
        self.service.run_cycle()
        self.client.pull(self.local)
        self.assertEqual(self.get.call_count, 2)
        self.assertIn("/mp3/", self.get.call_args.args[0])
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_a_previously_nonentry_delivery_does_not_block_a_new_local_audio_goal(self):
        self.get.side_effect = lambda url, **kwargs: response(SUGGESTIONS)
        self.ready()
        self.client.pull(self.local)
        self.local._save(
            "take", "html", HTML, 200, "https://www.diki.pl/slownik-angielskiego?q=take", True
        )
        self.assertEqual(self.client.submit(["take"], self.local)["queued"], 1)
        self.get.side_effect = lambda url, **kwargs: response(MP3)
        self.service.run_cycle()
        self.client.pull(self.local)
        self.assertEqual(self.get.call_count, 2)
        self.assertIn("/mp3/", self.get.call_args.args[0])
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_ready_unbatched_promotion_is_a_new_snapshot_generation(self):
        self.ready(need_audio=False)
        snapshot = self.service.begin_drain()
        self.service.submit([{"word": "take"}])
        self.service.run_cycle()
        self.assertIsNone(self.service.next_transfer(drain_id=snapshot["id"]))
        self.client.pull(self.local)
        self.assertEqual(self.get.call_count, 2)

    def test_terminal_failure_is_not_reset_by_priority_promotion(self):
        self.service.config.max_attempts = 1
        self.get.side_effect = requests.ReadTimeout("fake stall")
        self.service.submit([{"word": "take", "need_audio": False, "priority": "coverage"}])
        self.service.run_cycle()
        self.assertEqual(self.service.submit([{"word": "take"}])["alreadyKnown"], 1)
        self.clock.now += 10000
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 1)
        self.assertEqual(self.service.status()["jobs"], {"failed": 1})

    def test_one_finite_drain_imports_multiple_batches_but_excludes_later_work(self):
        self.service.config.batch_words = 20
        self.service.resources.interval = 0
        self.service.resources.jitter = 0
        self.get.side_effect = self.word_responses
        words = [f"word{index}" for index in range(12)]
        self.service.submit(
            [{"word": word, "need_audio": False, "priority": "coverage"} for word in words]
        )
        self.service.run_cycle()
        real_begin = self.service.begin_drain

        def begin():
            value = real_begin()
            self.service.submit([{"word": "later", "need_audio": False}])
            self.service.run_cycle()
            return value

        with patch.object(self.service, "begin_drain", side_effect=begin) as snapshot:
            result = self.client.pull(self.local, startup=True)
        self.assertEqual(result["wordsImported"], 12)
        self.assertEqual(result["transfersAcknowledged"], 2)
        snapshot.assert_called_once_with()
        self.assertIsNone(self.local._cached("later", "html"))
        self.assertEqual(self.service.status()["jobs"], {"delivered": 12, "ready": 1})

    def test_new_scheduling_requires_capability_instead_of_falling_back(self):
        with patch.object(self.client, "status", return_value={"protocol": 2}):
            with self.assertRaisesRegex(RemoteError, "Update the remote worker"):
                self.client.pull(self.local, startup=True)
        self.assertEqual(self.adapter.calls, [])

    def test_remembered_submissions_survive_reopen_and_goals_can_upgrade(self):
        result = self.client.submit(
            ["take"], self.local, html_only=True, priority="coverage", remember=True
        )
        self.assertEqual(result["queued"], 1)
        bodies = len(self.adapter.job_bodies)
        with DikiResources(self.local.root, offline=True) as reopened:
            result = self.client.submit(
                ["take"], reopened, html_only=True, priority="coverage", remember=True
            )
            self.assertEqual(result["alreadySubmitted"], 1)
            self.assertEqual(len(self.adapter.job_bodies), bodies)
            self.assertEqual(
                self.client.submit(["take"], reopened, priority="buffer", remember=True)["queued"],
                1,
            )
        self.service.run_cycle()
        self.client.pull(self.local)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_cancelled_drain_recovers_and_lost_ack_does_not_repeat_upstream_work(self):
        self.ready()
        stop = threading.Event()
        self.client.stop = stop
        real_contents = self.client._contents

        def contents(*args):
            value = real_contents(*args)
            stop.set()
            return value

        with patch.object(self.client, "_contents", side_effect=contents):
            with self.assertRaises(RemoteStopped):
                self.client.pull(self.local, startup=True)
        self.assertIsNone(self.local._cached("take", "html"))
        self.client.stop = None
        self.adapter.fail_ack_once = True
        with self.assertRaises(RemoteError):
            self.client.pull(self.local, startup=True)
        self.assertEqual(self.local.fetch_audio("take"), MP3)
        self.assertEqual(self.client.pull(self.local, startup=True)["wordsImported"], 1)
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.service.status()["storedBytes"], 0)

    def test_automatic_import_keeps_a_valid_snapshot_created_during_download(self):
        self.ready()
        local_html = HTML + b"<!-- independent retained snapshot -->"
        self.local._save(
            "take", "html", local_html, 200, "https://www.diki.pl/slownik-angielskiego?q=take", True
        )
        self.client.preserve_existing = True
        result = self.client.pull(self.local, startup=True)
        self.assertEqual(result["serverCleanupPending"], 0)
        self.assertEqual(self.local.fetch_html("take").encode(), local_html)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_network_transfer_never_holds_the_cache_lock(self):
        self.ready()
        original = self.adapter.send

        def send(request, **kwargs):
            if "/files/" in request.url:
                with file_lock(self.local.root / "cache.lock", blocking=False):
                    pass
            return original(request, **kwargs)

        with patch.object(self.adapter, "send", side_effect=send):
            self.client.pull(self.local, startup=True)


class TestPreparationCoordinator(RemoteFixture):
    def wait_for(self, predicate):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Background preparation did not reach the expected state")

    def finish(self, preparation):
        preparation.close()
        for thread in preparation.threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

    def test_exact_windows_and_replenishment_are_event_driven_and_deduplicated(self):
        folder = self.root / "words"
        folder.mkdir()
        words = [f"word{index}" for index in range(101)]
        main = folder / "words_to_add.txt"
        main.write_text("\n".join(words) + "\n")
        (folder / "book.txt").write_text("\n".join(["repeat"] * 100 + ["beyond"]) + "\n")

        def factory(**options):
            client = RemoteDownloads(fixtures.URL, fixtures.TOKEN, **options)
            client.session.mount(fixtures.URL, self.adapter)
            return client

        preparation = RemotePreparation(
            self.local.root,
            factory,
            words_dir=folder,
            inventory_loader=lambda: {"words": ["coverage"], "invalidCount": 0},
        )
        self.addCleanup(self.finish, preparation)
        preparation.start()
        self.wait_for(
            lambda: (
                preparation.status()["submission"] == "idle"
                and preparation.status()["drain"] == "complete"
            )
        )
        submitted = [item for body in self.adapter.job_bodies for item in body["items"]]
        self.assertEqual(len(submitted), 102)
        self.assertNotIn("beyond", [item["word"] for item in submitted])
        self.assertNotIn("word100", [item["word"] for item in submitted])
        self.assertEqual(submitted[-1]["priority"], "coverage")
        self.assertFalse(submitted[-1]["need_audio"])
        main.write_text("\n".join(words[1:]) + "\n")
        preparation.notify()
        self.wait_for(lambda: preparation.status()["queued"] == 103)
        self.assertEqual(
            self.adapter.job_bodies[-1]["items"],
            [{"word": "word100", "need_audio": True, "priority": "buffer"}],
        )
        self.assertEqual(sum(path == "/v1/transfers/drain" for _, path in self.adapter.calls), 1)
        self.get.assert_not_called()
        self.assertEqual(main.read_text(), "\n".join(words[1:]) + "\n")

    def test_shutdown_does_not_wait_for_a_blocked_download(self):
        entered, release = threading.Event(), threading.Event()
        clients = []

        def factory(**options):
            client = Mock()

            def pull(*args, **kwargs):
                entered.set()
                release.wait(5)
                return {"wordsImported": 0}

            client.pull.side_effect = pull
            client.submit.return_value = {"queued": 0}
            clients.append(client)
            return client

        preparation = RemotePreparation(
            self.local.root,
            factory,
            words_dir=self.root / "absent",
            inventory_loader=lambda: {"words": []},
        )
        preparation.start()
        try:
            self.assertTrue(entered.wait(3))
            before = time.monotonic()
            preparation.close()
            self.assertLess(time.monotonic() - before, 0.2)
            self.assertTrue(preparation.stop.is_set())
        finally:
            release.set()
            self.finish(preparation)
        self.assertTrue(all(client.close.call_count == 1 for client in clients))

    def test_unreadable_book_does_not_starve_readable_main_buffer(self):
        folder = self.root / "words"
        folder.mkdir()
        (folder / "words_to_add.txt").write_text("take\n")
        (folder / "broken.txt").write_bytes(b"\xff\xfe")
        preparation = RemotePreparation(
            self.local.root, Mock(), words_dir=folder, inventory_loader=lambda: {"words": []}
        )
        preparation.reconcile(self.client, self.local)
        self.assertEqual(self.service.status()["jobs"], {"queued": 1})
        self.assertEqual(preparation.status()["queued"], 1)
        self.assertIn("broken.txt", preparation.status()["submissionError"])

    def test_startup_imports_and_acknowledges_while_the_app_is_still_open(self):
        self.ready()
        folder = self.root / "words"
        folder.mkdir()
        (folder / "words_to_add.txt").write_text("take\n")

        def factory(**options):
            client = RemoteDownloads(fixtures.URL, fixtures.TOKEN, **options)
            client.session.mount(fixtures.URL, self.adapter)
            return client

        preparation = RemotePreparation(
            self.local.root, factory, words_dir=folder, inventory_loader=lambda: {"words": []}
        )
        self.addCleanup(self.finish, preparation)
        preparation.start()
        self.wait_for(lambda: preparation.status()["drain"] == "complete")
        self.assertFalse(preparation.stop.is_set())
        self.assertEqual(preparation.status()["wordsImported"], 1)
        self.assertEqual(self.local.fetch_audio("take"), MP3)
        self.assertEqual(self.service.status()["storedBytes"], 0)
        self.assertEqual(self.service.status()["jobs"], {"delivered": 1})

    def test_missing_remote_configuration_is_optional_and_partial_config_is_visible(self):
        with patch.dict(os.environ, {"DIKI_REMOTE_URL": "", "DIKI_REMOTE_TOKEN": ""}):
            self.assertIsNone(RemotePreparation.from_environment(self.local.root))
        with patch.dict(os.environ, {"DIKI_REMOTE_URL": fixtures.URL, "DIKI_REMOTE_TOKEN": ""}):
            preparation = RemotePreparation.from_environment(self.local.root)
        self.assertIsNotNone(preparation)
        assert preparation is not None
        self.addCleanup(self.finish, preparation)
        preparation.start()
        self.wait_for(
            lambda: (
                preparation.status()["submission"] == "error"
                and preparation.status()["drain"] == "error"
            )
        )
        self.assertIn("DIKI_REMOTE_TOKEN", preparation.status()["submissionError"])
        self.assertEqual(self.adapter.calls, [])


class TestInventoryAndWindows(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        environment = patch.dict(os.environ, {"ANKI_FACTORY_DATA_DIR": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)

    def test_occurrence_limit_precedes_deduplication_and_invalid_entries(self):
        main = self.root / "words_to_add.txt"
        main.write_text("\ufeff\n" + "same\n" * 98 + "Polish\npolish\nnever\n")
        book = self.root / "book.txt"
        book.write_text("x" * 501 + "\n" + "repeat\n" * 99 + "outside\n")
        outside = self.root.parent / "must-not-read.txt"
        (self.root / "outside.txt").symlink_to(outside)
        rows = discover_lists(self.root, entry_limit=100)
        self.assertEqual(rows[0].words, ["same", "Polish", "polish"])
        self.assertEqual(rows[0].entries, 100)
        self.assertEqual(rows[1].words, ["repeat"])
        self.assertEqual(rows[1].invalid, 1)
        self.assertEqual(len(rows), 2)

    def test_one_time_export_uses_contract_types_and_reports_invalid_fields(self):
        models = ["Basic [reverse+audio]", "Basic [reverse+audio+image]"]
        values = {
            1: (models[0], "Polish"),
            2: (models[0], "polish"),
            3: (models[1], "Polish"),
            4: (models[1], "<img src=x>"),
        }
        api = Mock(last_error=None)

        def invoke(action, **params):
            if action == "getActiveProfile":
                return "Main"
            if action == "findNotes":
                model = json.loads(params["query"][5:])
                self.assertIn(model, models)
                return [identifier for identifier, (name, _) in values.items() if name == model]
            if action == "notesInfo":
                return [
                    {
                        "noteId": identifier,
                        "modelName": values[identifier][0],
                        "fields": {"en_word": {"value": values[identifier][1]}},
                    }
                    for identifier in params["notes"]
                ]
            raise AssertionError(f"Unexpected collection operation: {action}")

        api.invoke.side_effect = invoke
        inventory = export_inventory(api)
        self.assertEqual(inventory["words"], ["Polish", "polish"])
        self.assertEqual(inventory["checked"], 4)
        self.assertEqual(inventory["invalidCount"], 1)
        save_inventory(inventory)
        api.reset_mock()
        self.assertEqual(load_inventory()["words"], inventory["words"])
        api.invoke.assert_not_called()
        self.assertFalse((self.root / "words_to_add").exists())

    def test_imported_word_file_is_case_preserving_and_invalid_input_does_not_replace_inventory(
        self,
    ):
        path = self.root / "export.txt"
        path.write_text("Polish\npolish\nPolish\n")
        import_inventory("export.txt")
        self.assertEqual(load_inventory()["words"], ["Polish", "polish"])
        path.write_text("bad  spacing\n")
        with self.assertRaises(ValueError):
            import_inventory("export.txt")
        self.assertEqual(load_inventory()["words"], ["Polish", "polish"])
