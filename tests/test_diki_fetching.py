import json
import signal
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest import TestCase
from unittest.mock import Mock, patch

from requests.adapters import BaseAdapter
from requests.exceptions import ConnectionError
from urllib3.exceptions import ReadTimeoutError

from external_apis.diki_api import DikiApi
from external_apis.diki_audio import DISCOVERY_VERSION, discover_audio_urls
from external_apis.diki_lists import WordList, coverage
from external_apis.diki_resources import (
    RECOVERY_SUCCESSES,
    Blocked,
    Deferred,
    DikiResources,
    DikiTimeout,
    NoAudio,
    file_lock,
)
from tests.test_diki_resources import HTML, MP3, Clock, response
from tools.diki_lookup import lookup_meanings, lookup_timeout
from tools.diki_prefetch import run_batch

CASES = Path(__file__).parent / "diki_cases"
CHALLENGE = b"<title>Just a moment...</title><div>Verify you are human</div>"


class TestAdvertisedAudio(TestCase):
    def fragment(self, name):
        return (CASES / f"audio-{name}.html").read_text(encoding="utf-8")

    def test_real_space_variant_does_not_select_synonym_or_sentence(self):
        html = self.fragment("eyepatch")
        self.assertEqual(
            discover_audio_urls(html, "eyepatch"),
            ["https://www.diki.pl/images-common/en/mp3/eye_patch.mp3"],
        )
        self.assertEqual(
            discover_audio_urls(html, "eye patch"),
            ["https://www.diki.pl/images-common/en/mp3/eye_patch.mp3"],
        )
        self.assertEqual(
            discover_audio_urls(html, "patch"),
            [
                "https://www.diki.pl/images-common/en/mp3/patch.mp3",
                "https://www.diki.pl/images-common/en-ame/mp3/patch.mp3",
            ],
        )

    def test_real_transcription_without_recording_has_no_guessed_urls(self):
        self.assertEqual(discover_audio_urls(self.fragment("revenant"), "revenant"), [])

    def test_real_inflection_is_not_confused_with_base_form(self):
        html = self.fragment("shone")
        self.assertEqual(
            discover_audio_urls(html, "shone"),
            ["https://www.diki.pl/images-common/en/mp3/shone.mp3"],
        )
        self.assertEqual(
            discover_audio_urls(html, "shine"),
            ["https://www.diki.pl/images-common/en/mp3/shine.mp3"],
        )

    def test_exact_spelling_precedes_space_variant_even_when_variant_is_british(self):
        html = """<div class="dictionaryEntity"><div class="hws">
            <span class="hw">eyepatch</span><span data-audio-url="/images-common/en-ame/mp3/eyepatch.mp3"></span>
            <br><span class="hw">eye patch</span><span data-audio-url="/images-common/en/mp3/eye_patch.mp3"></span>
            </div></div>"""
        self.assertEqual(
            discover_audio_urls(html, "eyepatch"),
            [
                "https://www.diki.pl/images-common/en-ame/mp3/eyepatch.mp3",
                "https://www.diki.pl/images-common/en/mp3/eye_patch.mp3",
            ],
        )

    def test_hyphen_changes_and_unmatched_entries_are_not_spelling_variants(self):
        html = """<div class="dictionaryEntity"><div class="hws">
            <span class="hw">resign</span><br><span class="hw">re-sign</span>
            <span data-audio-url="/images-common/en/mp3/re-sign.mp3"></span>
            </div></div>"""
        self.assertEqual(discover_audio_urls(html, "resign"), [])
        self.assertEqual(discover_audio_urls(html, "unrelated"), [])

    def test_nested_headwords_deduplicate_and_prefer_british(self):
        html = """<div class="dictionaryEntity"><div class="hws">
            <span class="hw">whatever floats <span class="stopword">one's</span> boat</span>
            <span><span data-audio-url="/images-common/en-ame/mp3/boat.mp3"></span>
            <span data-audio-url="/images-common/en/mp3/boat.mp3"></span>
            <span data-audio-url="/images-common/en/mp3/boat.mp3"></span></span>
            </div></div>"""
        self.assertEqual(
            discover_audio_urls(html, "whatever floats one's boat"),
            [
                "https://www.diki.pl/images-common/en/mp3/boat.mp3",
                "https://www.diki.pl/images-common/en-ame/mp3/boat.mp3",
            ],
        )

    def test_remote_html_cannot_choose_arbitrary_hosts_or_paths(self):
        for url in [
            "https://example.com/test.mp3",
            "//localhost/test.mp3",
            "http://www.diki.pl/images-common/en/mp3/take.mp3",
            "https://user:pass@www.diki.pl/images-common/en/mp3/take.mp3",
            "/images-common/en/mp3/%2e%2e%2ftake.mp3",
            "/images-common/en/mp3/take%0a.mp3",
            "https://[invalid",
            "/images-common/en/mp3/take.mp3?redirect=elsewhere",
        ]:
            with self.subTest(url=url):
                html = f'<div class="dictionaryEntity"><div class="hws"><span class="hw">take</span><span data-audio-url="{url}"></span></div></div>'
                self.assertEqual(discover_audio_urls(html, "take"), [])


class TestFetchProfiles(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.clock = Clock()

    def resources(self, profile="background", **kwargs) -> Any:
        # Tests deliberately inspect the injected mock transport.
        defaults: dict[str, Any] = {
            "profile": profile,
            "clock": self.clock,
            "sleep": self.clock.sleep,
            "uniform": lambda low, high: (low + high) / 2,
            "jitter": 0,
            "get": Mock(side_effect=lambda *args, **kwargs: response()),
        }
        defaults.update(kwargs)
        result = DikiResources(self.root, **defaults)
        self.addCleanup(result.close)
        return result

    def test_background_lock_pause_and_retry_do_not_block_interactive_fetch(self):
        background = self.resources(get=Mock(return_value=response(CHALLENGE)))
        with self.assertRaises(Blocked):
            background.fetch_html("take")
        interactive = self.resources("interactive")
        self.assertEqual(interactive.metadata("take", "html")["attempts"], 0)
        with file_lock(background.request_lock):
            self.assertTrue(interactive.fetch_html("take"))
        interactive.get.assert_called_once()
        self.assertEqual(self.clock.waits, [])
        background.get.reset_mock()
        self.assertTrue(background.fetch_html("take"))
        background.get.assert_not_called()  # successful artifacts remain shared
        self.assertIsNot(background.session, interactive.session)

    def test_existing_pause_does_not_wait_request_or_create_word_failures(self):
        resources = self.resources()
        resources._cooldown(100, "Previous challenge")
        with file_lock(resources.request_lock):
            for _ in range(2):
                with self.assertRaisesRegex(Deferred, "paused until"):
                    resources.fetch_html("take")
        self.assertIsNone(resources.metadata("take", "html"))
        self.assertEqual(resources.setting("request_counts", {}), {})
        self.assertEqual(self.clock.waits, [])
        resources.get.assert_not_called()

    def test_batch_distinguishes_new_challenge_from_later_paused_run(self):
        resources = self.resources(get=Mock(return_value=response(CHALLENGE)))
        lists = [WordList("main.txt", ["take"], 1)]
        first = run_batch(resources, lists)
        again = run_batch(resources, lists)
        self.assertEqual((first["status"], first["errors"]), ("cooldown", 1))
        self.assertEqual((again["status"], again["errors"], again["attempted"]), ("paused", 0, 0))
        self.assertIn("no request attempted", again["message"])
        self.assertEqual(resources.metadata("take", "html")["attempts"], 1)
        self.assertEqual(resources.get.call_count, 1)

    def test_recovery_is_paced_and_decays_after_sustained_success(self):
        get = Mock(return_value=response(CHALLENGE))
        resources = self.resources(get=get)
        with self.assertRaises(Blocked):
            resources.fetch_html("blocked")
        self.assertEqual(resources._interval(), 40)
        self.assertTrue(resources.setting("recovery_pending"))
        # A separate scheduled run retains pacing and makes just one first probe.
        self.clock.now = resources.setting("cooldown_until") + 1
        resources = self.resources()
        resources.fetch_html("recovered")
        self.assertTrue(resources.setting("last_request")["recoveryProbe"])
        self.assertFalse(resources.setting("recovery_pending"))
        self.assertEqual(resources.setting("next_request_at"), self.clock() + 40)
        for index in range(RECOVERY_SUCCESSES - 1):
            resources.fetch_html(f"other-{index}")
        self.assertEqual(self.clock.waits, [40] * (RECOVERY_SUCCESSES - 1))
        self.assertEqual(resources._interval(), 20)
        self.assertEqual(resources.setting("challenge_streak"), 0)

    def test_repeated_challenges_increase_pause_and_respect_retry_after(self):
        resources = self.resources(get=Mock(return_value=response(CHALLENGE)))
        with self.assertRaises(Blocked):
            resources.fetch_html("one")
        self.clock.now = resources.setting("cooldown_until") + 1
        resources.get.return_value = response(b"slow down", 429, {"Retry-After": "90000"})
        with self.assertRaises(Blocked):
            resources.fetch_html("two")
        self.assertEqual(resources._interval(), 80)
        self.assertEqual(resources.setting("cooldown_until"), self.clock() + 90000)
        self.assertEqual(resources.setting("request_counts"), {"challenge": 1, "rate_limited": 1})

    def test_diagnostics_keep_response_evidence_but_not_cookies_or_body(self):
        resources = self.resources(
            get=Mock(
                return_value=response(
                    CHALLENGE,
                    headers={
                        "CF-Ray": "test-ray",
                        "Content-Type": "text/html",
                        "Set-Cookie": "secret=value",
                    },
                )
            )
        )
        with self.assertRaises(Blocked):
            resources.fetch_html("take")
        event = resources.setting("last_request")
        self.assertEqual(event["status"], 200)
        self.assertEqual(event["title"], "Just a moment...")
        self.assertEqual(event["outcome"], "challenge")
        self.assertEqual(event["headers"]["CF-Ray"], "test-ray")
        self.assertNotIn("secret", json.dumps(event))
        self.assertNotIn("<div>", json.dumps(event))
        with resources.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM request_events").fetchone()[0], 1)

    def test_streamed_read_timeout_is_not_a_global_connection_failure(self):
        result = response()
        result.iter_content = Mock(
            side_effect=ConnectionError(ReadTimeoutError(cast(Any, None), "/", "read timed out"))
        )
        resources = self.resources(get=Mock(return_value=result))
        with self.assertRaisesRegex(DikiTimeout, "response body stalled"):
            resources.fetch_html("take")
        self.assertEqual(resources.setting("cooldown_until", 0), 0)
        self.assertEqual(resources.setting("last_request")["outcome"], "timeout")

    def test_mp3_metadata_containing_challenge_words_is_not_a_block_page(self):
        audio = MP3 + b"just a moment... access denied"
        resources = self.resources(get=Mock(return_value=response(audio)))
        resources._save("take", "html", HTML, 200, "fixture", True)
        self.assertEqual(resources.fetch_audio("take"), audio)
        self.assertEqual(resources.setting("cooldown_until", 0), 0)

    def test_challenge_response_retry_after_can_extend_the_pause(self):
        resources = self.resources(
            get=Mock(return_value=response(CHALLENGE, headers={"Retry-After": "90000"}))
        )
        with self.assertRaises(Blocked):
            resources.fetch_html("take")
        self.assertEqual(resources.setting("cooldown_until"), self.clock() + 90000)

    def test_legacy_state_moves_to_background_once_and_preserves_cache(self):
        original = self.resources()
        original._save("take", "html", HTML, 200, "fixture", True)
        with original.db() as db:
            db.execute("DELETE FROM settings")
            db.execute("INSERT INTO settings VALUES ('cooldown_until','99999')")
            db.execute("INSERT INTO settings VALUES ('cooldown_reason','\"Old challenge\"')")
            db.execute("""INSERT INTO resources(word,kind,state,error,attempts,retry_at)
                VALUES ('old-error','html','error','Old timeout',3,5000)""")
            db.execute(
                "INSERT INTO resources(word,kind,state,cursor) VALUES ('eyepatch','audio','no_audio',6)"
            )
        interactive = self.resources("interactive")
        background = self.resources()
        self.assertEqual(interactive.setting("cooldown_until", 0), 0)
        self.assertEqual(background.setting("cooldown_until"), 99999)
        self.assertEqual(background.metadata("old-error", "html")["attempts"], 3)
        self.assertEqual(interactive.metadata("old-error", "html")["attempts"], 0)
        self.assertEqual(background.metadata("eyepatch", "audio")["state"], "pending")
        self.assertTrue(interactive.fetch_html("take"))
        self.assertTrue(background.fetch_html("take"))

    def test_coverage_always_reports_background_state_when_read_by_app(self):
        background = self.resources()
        background._cooldown(100, "Background challenge")
        background.set_setting("last_run", {"status": "paused"})
        interactive = self.resources("interactive")
        interactive._cooldown(50, "Interactive pause")
        report = coverage(interactive, [])
        self.assertEqual(report["cooldownReason"], "Background challenge")
        self.assertEqual(report["lastRun"], {"status": "paused"})

    def test_each_word_finishes_html_and_audio_before_next_word(self):
        def get(url, **kwargs):
            return response(
                MP3
                if "/mp3/" in url
                else HTML.replace(b"take", b"other")
                if "q=other" in url
                else HTML
            )

        resources = self.resources(get=Mock(side_effect=get))
        result = run_batch(resources, [WordList("main.txt", ["take", "other"], 2)])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(
            [call.args[0] for call in resources.get.call_args_list],
            [
                "https://www.diki.pl/slownik-angielskiego?q=take",
                "https://www.diki.pl/images-common/en/mp3/take.mp3",
                "https://www.diki.pl/slownik-angielskiego?q=other",
                "https://www.diki.pl/images-common/en/mp3/other.mp3",
            ],
        )

    def test_legacy_no_audio_is_reconsidered_using_cached_html_only(self):
        resources = self.resources(get=Mock(return_value=response(MP3)))
        html = (CASES / "audio-eyepatch.html").read_bytes()
        resources._save("eyepatch", "html", html, 200, "fixture", True)
        with resources.db() as db:
            db.execute(
                "INSERT INTO resources(word,kind,state,cursor) VALUES ('eyepatch','audio','no_audio',6)"
            )
        self.assertEqual(resources.fetch_audio("eyepatch"), MP3)
        resources.get.assert_called_once()
        self.assertTrue(resources.get.call_args.args[0].endswith("/eye_patch.mp3"))

    def test_absent_recording_is_shared_and_revisited_after_html_changes(self):
        resources = self.resources()
        resources._save(
            "revenant", "html", (CASES / "audio-revenant.html").read_bytes(), 200, "fixture", True
        )
        with self.assertRaises(NoAudio):
            resources.fetch_audio("revenant")
        resources.get.assert_not_called()
        other = self.resources("interactive", offline=True)
        with self.assertRaises(NoAudio):
            other.fetch_audio("revenant")
        resources._save(
            "revenant", "html", HTML.replace(b"take", b"revenant"), 200, "fixture", True
        )
        resources.get.side_effect = None
        resources.get.return_value = response(MP3)
        self.assertEqual(resources.fetch_audio("revenant"), MP3)

    def test_new_discovery_version_reconsiders_previous_negative(self):
        resources = self.resources(get=Mock(return_value=response(MP3)))
        resources._save("take", "html", HTML, 200, "fixture", True)
        plan = resources._audio_plan("take", HTML.decode())
        with resources.db() as db:
            db.execute("INSERT INTO resources(word,kind,state) VALUES ('take','audio','no_audio')")
            db.execute("UPDATE audio_discovery SET version=?,exhausted=1", (DISCOVERY_VERSION - 1,))
        self.assertEqual(resources.fetch_audio("take"), MP3)
        self.assertEqual(resources._audio_plan("take", HTML.decode())["version"], DISCOVERY_VERSION)
        self.assertEqual(plan["html_digest"], resources.metadata("take", "html")["digest"])

    def test_failed_audio_refresh_never_prevents_repairing_a_positive_cache(self):
        resources = self.resources(get=Mock(return_value=response(MP3)))
        resources._save("take", "html", HTML, 200, "fixture", True)
        resources.fetch_audio("take")
        resources.get.side_effect = [response(b"missing", 404), response(b"missing", 404)]
        with self.assertRaises(NoAudio):
            resources.fetch_audio("take", refresh=True)
        self.assertEqual(resources.fetch_audio("take"), MP3)
        resources.path("take", "audio").unlink()
        resources.get.side_effect = None
        resources.get.return_value = response(MP3)
        self.assertEqual(resources.fetch_audio("take"), MP3)

    def test_concurrent_profile_writes_keep_file_and_metadata_consistent(self):
        first = self.resources()
        second = self.resources("interactive")
        barrier = threading.Barrier(2)

        def save(resources, content):
            barrier.wait(timeout=5)
            resources._save("take", "html", content, 200, "fixture", True)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(save, first, HTML),
                executor.submit(save, second, HTML + b"<!-- newer -->"),
            ]
            for future in futures:
                future.result(timeout=5)
        self.assertIn(first.fetch_html("take").encode(), [HTML, HTML + b"<!-- newer -->"])
        self.assertEqual(first.snapshot()[("take", "html")]["state"], "ready")


class CookieAdapter(BaseAdapter):
    """Exercise real Requests cookie preparation/extraction, without the network."""

    def __init__(self):
        self.requests = []
        self.closed = False

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        self.requests.append(request)
        result = response()
        result.request = request
        result.url = request.url
        message = Message()
        message.add_header("Set-Cookie", "diki_test=session-value; Path=/; Secure; HttpOnly")
        result.raw._original_response = SimpleNamespace(msg=message)
        return result

    def close(self):
        self.closed = True


class TestSessionAndCliDeadline(TestCase):
    def test_real_session_retains_server_cookies_between_fetches_and_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = CookieAdapter()
            with DikiResources(directory, interval=0) as resources:
                resources.session.mount("https://www.diki.pl/", adapter)
                resources.fetch_html("take")
                resources.fetch_html("other")
            self.assertNotIn("Cookie", adapter.requests[0].headers)
            self.assertEqual(adapter.requests[1].headers["Cookie"], "diki_test=session-value")
            self.assertTrue(adapter.closed)

    def test_cli_deadline_stops_trickled_body_and_restores_signal_handler(self):
        result = response()
        result.close = Mock()

        def trickle(chunk_size):
            while True:
                time.sleep(0.005)
                yield b" "

        result.iter_content = trickle
        previous = signal.getsignal(signal.SIGALRM)
        with tempfile.TemporaryDirectory() as directory:
            with DikiResources(directory, get=Mock(return_value=result)) as resources:
                api = DikiApi(resources)
                with patch(
                    "tools.diki_lookup.lookup_timeout", side_effect=lambda: lookup_timeout(0.03)
                ):
                    self.assertEqual(lookup_meanings(api, "take"), [])
                self.assertIn("timed out", cast(str, api.last_error))
                self.assertEqual(resources.setting("last_request")["outcome"], "timeout")
                result.close.assert_called_once()
                self.assertEqual(signal.getsignal(signal.SIGALRM), previous)
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_cli_deadline_bounds_lock_wait_without_starting_a_request(self):
        with tempfile.TemporaryDirectory() as directory:
            with DikiResources(directory, get=Mock()) as resources:
                with file_lock(resources.request_lock):
                    with self.assertRaisesRegex(DikiTimeout, "timed out"), lookup_timeout(0.03):
                        resources.fetch_html("take")
                cast(Mock, resources.get).assert_not_called()
                self.assertIsNone(resources.metadata("take", "html"))
