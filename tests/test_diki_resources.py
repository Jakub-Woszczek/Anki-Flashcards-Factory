import io
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import requests

from backend.services import FactoryService, ServiceError
from external_APIs.dikiApi import DikiApi
from external_APIs.diki_lists import WordList, coverage, discover_lists
from external_APIs.diki_resources import (
    BLOCK_COOLDOWN, BatchDeadline, Blocked, CacheMiss, Deferred,
    DikiResources, DikiServerError, DikiTimeout, NoAudio, ResourceError, file_lock,
)
from tools.diki_launchd import configuration
from tools.diki_prefetch import run_batch


HTML = (Path(__file__).parent / "diki_cases" / "take.html").read_bytes()
MP3 = b"ID3\x04\x00\x00test-pronunciation"
SUGGESTIONS = b'<div class="dictionarySuggestions"><a>take</a></div>'


def response(content=HTML, status=200, headers=None):
    result = requests.Response()
    result.status_code = status
    result.raw = io.BytesIO(content)
    result.headers.update(headers or {})
    return result


class Clock:
    def __init__(self):
        self.now = 1000
        self.waits = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class TestDikiResources(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.clock = Clock()
        self.get = Mock(return_value=response())

    def resources(self, **kwargs):
        defaults = dict(clock=self.clock, sleep=self.clock.sleep,
                        uniform=lambda low, high: 20, get=self.get)
        defaults.update(kwargs)
        return DikiResources(self.root / "cache", **defaults)

    def test_disk_cache_is_shared_and_offline_hits_never_wait_or_request(self):
        resources = self.resources()
        api = DikiApi(resources)
        self.assertTrue(api.get_meanings(" TAKE "))
        other = self.resources(offline=True)
        other.set_setting("cooldown_until", 999999)
        self.assertTrue(DikiApi(other).get_translations("take"))
        self.assertIn("take", {word.lower() for word in DikiApi(other).possible_spellings("take")})
        self.assertEqual(self.get.call_count, 1)
        self.assertEqual(self.clock.waits, [])
        with self.assertRaises(CacheMiss):
            other.fetch_html("uncached")
        with self.assertRaises(CacheMiss):
            other.fetch_audio("uncached")
        self.assertEqual(self.get.call_count, 1)

    def test_404_suggestions_are_cached_once_but_not_exact_matches(self):
        self.get.return_value = response(SUGGESTIONS, 404)
        resources = self.resources()
        api = DikiApi(resources)
        self.assertEqual(api.get_meanings("tkae"), [])
        self.assertEqual(api.possible_spellings("tkae"), {"take"})
        self.assertEqual(self.get.call_count, 1)
        row = resources.metadata("tkae", "html")
        self.assertEqual((row["status"], row["exact_match"]), (404, 0))

    def test_real_dictionary_with_cloudflare_detection_script_is_not_a_block_page(self):
        content = HTML + b'''<script>(function(){var u='/cdn-cgi/challenge-platform/scripts/jsd/main.js';})();</script>'''
        self.get.return_value = response(content)
        resources = self.resources()
        self.assertTrue(DikiApi(resources).lookup("take")[0])
        self.assertEqual(resources.metadata("take", "html")["state"], "ready")
        self.assertEqual(resources.setting("cooldown_until", 0), 0)

    def test_origin_read_timeout_is_visible_and_does_not_pause_unrelated_words(self):
        self.get.side_effect = requests.ReadTimeout("Origin did not send HTTP headers")
        resources = self.resources()
        with self.assertRaisesRegex(DikiTimeout, "ReadTimeout.*15s.*HTTP headers"):
            resources.fetch_html("stalled")
        self.assertEqual(resources.setting("cooldown_until", 0), 0)
        self.assertIn("ReadTimeout", resources.metadata("stalled", "html")["error"])
        self.get.side_effect = None
        self.get.return_value = response()
        self.assertTrue(resources.fetch_html("take"))
        self.assertEqual(self.clock.waits, [20])

    def test_524_is_an_origin_error_and_retry_after_is_honored(self):
        resources = self.resources()
        self.get.return_value = response(b"Cloudflare origin timed out", 524)
        with self.assertRaisesRegex(DikiServerError, "HTTP 524.*origin server"):
            resources.fetch_html("take")
        self.assertEqual(resources.setting("cooldown_until", 0), 0)
        self.get.return_value = response(b"Service unavailable", 503, {"Retry-After": "600"})
        with self.assertRaisesRegex(DikiServerError, "HTTP 503"):
            resources.fetch_html("other")
        self.assertEqual(resources.setting("cooldown_until"), self.clock() + 600)

    def test_batch_continues_after_one_slow_word_and_saves_other_resources(self):
        self.get.side_effect = [requests.ReadTimeout("Slow origin"), response(), response(MP3)]
        resources = self.resources()
        result = run_batch(resources, [WordList("words_to_add.txt", ["stalled", "take"], 2)])
        self.assertEqual(result["status"], "partial")
        self.assertEqual((result["attempted"], result["html"], result["audio"], result["errors"]), (2, 1, 1, 1))
        self.assertTrue(resources.metadata("take", "html")["exact_match"])
        self.assertEqual(resources.fetch_audio("take"), MP3)
        self.assertEqual(resources.setting("cooldown_until", 0), 0)

    def test_batch_stops_after_three_consecutive_server_timeouts(self):
        self.get.side_effect = requests.ReadTimeout("Slow origin")
        resources = self.resources()
        result = run_batch(resources, [WordList("words_to_add.txt", ["one", "two", "three", "four"], 4)])
        self.assertEqual((result["status"], result["attempted"], result["errors"]), ("cooldown", 3, 3))
        self.assertEqual(self.get.call_count, 3)
        self.assertIn("ReadTimeout", result["message"])
        self.assertGreater(resources.setting("cooldown_until"), self.clock())

    def test_pacing_is_resampled_after_completion_and_persists_between_instances(self):
        calls = []

        def get(*args, **kwargs):
            calls.append(self.clock())
            self.clock.now += 3  # response time must not consume the spacing delay
            return response(MP3 if "/mp3/" in args[0] else HTML)

        jitter = Mock(side_effect=[15, 25, 20])
        resources = self.resources(get=get, uniform=jitter)
        resources.fetch_html("take")
        # A separate process/provider must observe the persisted random deadline.
        other = self.resources(get=get, uniform=jitter)
        other.fetch_audio("take")
        other.fetch_html("other")
        self.assertEqual(calls, [1000, 1018, 1046])
        self.assertEqual(self.clock.waits, [15, 25])
        self.assertEqual([call.args for call in jitter.call_args_list], [(15, 25)] * 3)

    def test_rate_limit_and_200_challenge_stop_requests_without_poisoning_cache(self):
        for content, status, headers in [
            (b"rate limited", 429, {"Retry-After": "30000"}),
            (b"forbidden", 403, {}),
            (b"<title>Just a moment...</title><script src='/cdn-cgi/challenge-platform/x'></script>", 200, {}),
        ]:
            with self.subTest(status=status):
                resources = DikiResources(self.root / str(status) / str(len(content)),
                                          clock=self.clock, sleep=self.clock.sleep,
                                          get=Mock(return_value=response(content, status, headers)))
                with self.assertRaises(Blocked):
                    resources.fetch_html("take")
                self.assertFalse(resources.path("take", "html").exists())
                self.assertGreaterEqual(resources.setting("cooldown_until"), self.clock() + BLOCK_COOLDOWN)
                with self.assertRaises(Deferred):
                    resources.fetch_html("other")
                self.assertEqual(resources.get.call_count, 1)

    def test_timeout_is_retryable_and_batch_does_not_treat_it_as_not_found(self):
        self.get.side_effect = requests.Timeout("timed out")
        resources = self.resources()
        with self.assertRaises(ResourceError):
            resources.fetch_html("take")
        row = resources.metadata("take", "html")
        self.assertEqual(row["state"], "error")
        self.assertGreater(row["retry_at"], self.clock())
        self.assertEqual(resources.snapshot()[("take", "html")]["state"], "error")
        with self.assertRaises(Deferred):
            resources.fetch_html("take")
        self.assertEqual(self.get.call_count, 1)

    def test_failed_refresh_keeps_last_good_html(self):
        resources = self.resources()
        resources.fetch_html("take")
        self.get.side_effect = requests.Timeout()
        with self.assertRaises(ResourceError):
            resources.fetch_html("take", refresh=True)
        resources.offline = True
        self.assertEqual(resources.fetch_html("take").encode(), HTML)

    def test_audio_fallback_is_paced_and_no_recording_is_terminal_until_refresh(self):
        self.get.side_effect = [response(b"not found", 404) for _ in range(3)] + [response(MP3)]
        resources = self.resources()
        self.assertEqual(resources.fetch_audio("streamline"), MP3)
        self.assertEqual([call.args[0].split("/images-common/")[1] for call in self.get.call_args_list],
                         ["en/mp3/streamline.mp3", "en/mp3/streamline-v.mp3",
                          "en/mp3/streamline-n.mp3", "en-ame/mp3/streamline.mp3"])
        self.assertEqual(self.clock.waits, [20, 20, 20])
        self.get.side_effect = [response(b"not found", 404) for _ in range(6)]
        with self.assertRaises(NoAudio):
            resources.fetch_audio("missing")
        self.assertEqual(resources.metadata("missing", "audio")["state"], "no_audio")
        count = self.get.call_count
        with self.assertRaises(NoAudio):
            resources.fetch_audio("missing")
        self.assertEqual(self.get.call_count, count)
        self.get.side_effect = [response(MP3)]
        self.assertEqual(resources.fetch_audio("missing", refresh=True), MP3)

    def test_invalid_mp3_and_corrupt_cache_are_not_reported_ready(self):
        self.get.return_value = response(b"<html>not audio</html>")
        resources = self.resources()
        with self.assertRaisesRegex(ResourceError, "invalid MP3"):
            resources.fetch_audio("take")
        self.assertFalse(resources.path("take", "audio").exists())
        resources._save("take", "html", HTML, 200, "fixture", True)
        resources.path("take", "html").write_bytes(b"X" * len(HTML))
        resources.offline = True
        with self.assertRaises(CacheMiss):
            resources.fetch_html("take")
        self.assertEqual(resources.snapshot()[("take", "html")]["state"], "missing")

    def test_concurrent_cache_misses_fetch_once(self):
        get = Mock(side_effect=lambda *args, **kwargs: response())
        first = self.resources(get=get, interval=0)
        second = self.resources(get=get, interval=0)
        barrier = threading.Barrier(2)

        def fetch(resources):
            barrier.wait(timeout=5)
            return resources.fetch_html("take")

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(fetch, resource) for resource in (first, second)]
            self.assertEqual([future.result(timeout=10) for future in futures], [HTML.decode()] * 2)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(list((first.root / "html").glob(".download-*")), [])

    def test_query_is_encoded_and_cache_paths_cannot_traverse(self):
        resources = self.resources()
        resources.fetch_html("a & b? #")
        self.assertIn("q=a+%26+b%3F+%23", self.get.call_args.args[0])
        self.assertTrue(self.get.call_args.kwargs["headers"]["User-Agent"].startswith("Mozilla/5.0"))
        self.assertEqual(resources.path("../../outside", "audio").parent, resources.root / "audio")

    def test_missing_positive_audio_restarts_variants_instead_of_becoming_a_false_miss(self):
        resources = self.resources()
        resources._save("take", "audio", MP3, 200, "fixture")
        with resources.db() as db:
            db.execute("UPDATE resources SET cursor=6 WHERE word='take' AND kind='audio'")
        resources.path("take", "audio").unlink()
        self.get.return_value = response(MP3)
        self.assertEqual(resources.fetch_audio("take"), MP3)
        self.assertTrue(self.get.call_args.args[0].endswith("/take.mp3"))

    def test_prefetch_resumes_audio_variant_after_runtime_limit(self):
        self.get.side_effect = [response(), response(b"missing", 404)]
        resources = self.resources(deadline=1040)
        lists = [WordList("words_to_add.txt", ["take"], 1)]
        summary = run_batch(resources, lists)
        self.assertEqual(summary["status"], "time_limit")
        self.assertEqual(summary["html"], 1)
        self.assertEqual(resources.metadata("take", "audio")["cursor"], 1)
        self.get.side_effect = [response(MP3)]
        resumed = self.resources(deadline=self.clock() + 300)
        summary = run_batch(resumed, lists)
        self.assertEqual(summary["status"], "complete")
        self.assertEqual((summary["html"], summary["audio"]), (0, 1))
        self.assertTrue(self.get.call_args.args[0].endswith("/take-v.mp3"))
        self.get.reset_mock()
        self.assertEqual(run_batch(resumed, lists)["attempted"], 0)
        self.get.assert_not_called()

    def test_job_lock_prevents_overlapping_batches(self):
        resources = self.resources()
        with file_lock(resources.root / "prefetch.lock", blocking=False):
            summary = run_batch(resources, [WordList("a.txt", ["take"], 1)])
        self.assertEqual(summary["status"], "already_running")
        self.get.assert_not_called()

    def test_word_lists_deduplicate_prioritize_and_report_local_coverage(self):
        folder = self.root / "lists"
        (folder / "books").mkdir(parents=True)
        (folder / "words_to_add.txt").write_text(" TAKE \ntake\n\n tkae\n", encoding="utf-8")
        (folder / "books" / "book.txt").write_text("Take\n", encoding="utf-8")
        (folder / "broken.txt").write_bytes(b"\xff\xfe")
        (folder / "outside.txt").symlink_to(self.root / "outside.txt")
        (self.root / "outside.txt").write_text("secret", encoding="utf-8")
        lists = discover_lists(folder)
        self.assertEqual(lists[0].name, "words_to_add.txt")
        self.assertEqual(lists[0].words, ["take", "tkae"])
        self.assertEqual(len(lists), 3)
        resources = self.resources()
        resources._save("take", "html", HTML, 200, "fixture", True)
        resources._save("take", "audio", MP3, 200, "fixture")
        resources._save("tkae", "html", SUGGESTIONS, 404, "fixture")
        result = coverage(resources, lists)
        main, book, broken = result["lists"]
        self.assertEqual((main["entries"], main["total"], main["html"], main["ready"], main["percent"]),
                         (3, 2, 2, 1, 50))
        self.assertEqual(main["noExactMatch"], 1)
        self.assertEqual(book["percent"], 100)
        self.assertTrue(broken["error"])
        self.get.assert_not_called()
        self.assertEqual(run_batch(resources, lists)["attempted"], 0)
        self.get.assert_not_called()

    def test_cached_resources_can_create_anki_note_without_network_or_media_directory(self):
        resources = self.resources(offline=True)
        resources._save("take", "html", HTML, 200, "fixture", True)
        resources._save("take", "audio", MP3, 200, "fixture")
        service = FactoryService.__new__(FactoryService)
        service.diki = DikiApi(resources)
        service.diki.audio_path = None
        service.anki = Mock(last_error=None)
        service.anki.add_note.return_value = 123
        service.anki.store_media_file.return_value = "take.mp3"
        service.anki.sync.return_value = False  # Internet-offline AnkiWeb sync
        service.notes = Mock()
        target = {"deckName": "English", "modelName": "Basic", "fieldMapping": {"audioField": "Audio"}}
        self.assertTrue(service.diki.get_translations("take"))
        result = service._perform_commit(target, {"Front": "take", "Audio": "[sound:take.mp3]"},
                                         [], [], "create", None, "take", None, None)
        self.assertEqual(result["noteId"], 123)
        self.assertTrue(result["audioDownloaded"])
        self.assertTrue(result["syncPending"])
        service.anki.store_media_file.assert_called_once_with("take.mp3", MP3)
        self.get.assert_not_called()

    def test_offline_update_preserves_existing_sound_and_does_not_add_no_audio_tag(self):
        service = FactoryService.__new__(FactoryService)
        service.diki = DikiApi(self.resources(offline=True))
        service.anki = Mock(last_error=None)
        service.notes = Mock()
        existing = {"modelName": "Basic", "fields": {"Audio": {"value": "[sound:old.mp3]"}}, "tags": []}
        target = {"deckName": "English", "modelName": "Basic", "fieldMapping": {"audioField": "Audio"}}
        with patch.object(service, "_note_details", return_value={"note": existing}):
            service._perform_commit(target, {"Back": "brać", "Audio": "[sound:take.mp3]"},
                                    [], [], "update", 123, "take", None, None)
        service.anki.update_note_fields.assert_called_once_with(123, {"Back": "brać"})
        service.anki.add_tag_to_note.assert_not_called()
        self.get.assert_not_called()

    def test_lookup_reports_offline_miss_instead_of_spelling_failure(self):
        service = FactoryService.__new__(FactoryService)
        service.diki = DikiApi(self.resources(offline=True))
        service.notes = Mock()
        service.notes.get_note_id.return_value = None
        with self.assertRaisesRegex(ServiceError, "not cached"):
            service.review_item_lookup("take", {})
        self.get.assert_not_called()

    def test_launchd_configuration_is_independent_and_bounded(self):
        config = configuration()
        self.assertTrue(Path(config["ProgramArguments"][0]).is_absolute())
        self.assertEqual(config["StartInterval"], 1800)
        self.assertTrue(config["RunAtLoad"])
        self.assertIn("tools.diki_prefetch", config["ProgramArguments"])
        self.assertIn("600", config["ProgramArguments"])
