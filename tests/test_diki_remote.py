import copy
import gzip
import hashlib
import io
import json
import os
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

import requests
from fastapi.testclient import TestClient
from requests.adapters import BaseAdapter

from deploy.northflank.app import create_app
from deploy.northflank.config import Config
from deploy.northflank.service import BoundedResponse, DownloadService
from external_apis.diki_audio import DISCOVERY_VERSION, discover_audio_urls
from external_apis.diki_remote import RemoteDownloads, RemoteError
from external_apis.diki_resources import DikiResources, DikiTimeout
from external_apis.diki_transfer import MAX_MANIFEST_BYTES, canonical, digest, validate_manifest
from tests.test_diki_resources import HTML, MP3, SUGGESTIONS, Clock, response

TOKEN = "test-only-northflank-token-" * 3
URL = "https://remote-downloads.example"


class ApiAdapter(BaseAdapter):
    """Exercise the real API/client protocol without contacting Diki or a host."""

    def __init__(self, api):
        self.api, self.calls = api, []
        self.job_bodies, self.blob_bytes = [], 0
        self.fail_ack_once = False
        self.fail_blob_once: str | None = None
        self.corrupt_blob_once = False
        self.tamper_manifest = False

    def send(self, request: Any, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        path = urlsplit(request.url).path
        self.calls.append((request.method, path))
        if path == "/v1/jobs":
            self.job_bodies.append(json.loads(request.body))
        if self.fail_blob_once and path.endswith(self.fail_blob_once):
            self.fail_blob_once = None
            raise requests.ConnectionError("Simulated interrupted transfer")
        result = self.api.request(
            request.method,
            path + ("?" + urlsplit(request.url).query if urlsplit(request.url).query else ""),
            headers=dict(request.headers),
            content=request.body,
            follow_redirects=False,
        )
        if self.fail_ack_once and path.endswith("/ack"):
            self.fail_ack_once = False
            raise requests.ConnectionError("ACK committed, but its response was lost")
        body = result.content
        if "/files/" in path:
            self.blob_bytes += len(body)
        if self.corrupt_blob_once and "/files/" in path:
            self.corrupt_blob_once = False
            body = b"x" + body[1:]
        if self.tamper_manifest and path.endswith("/next") and result.status_code == 200:
            envelope = result.json()
            envelope["manifest"]["items"][0]["id"] = "../../escape"
            envelope["digest"] = digest(envelope["manifest"])
            body = json.dumps(envelope).encode()
        converted = requests.Response()
        converted.status_code = result.status_code
        converted.headers.update(result.headers)
        converted.raw = io.BytesIO(body)
        converted.url, converted.request = request.url, request
        return converted

    def close(self):
        pass


class TestRemoteDownloads(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.clock = Clock()
        self.get = Mock(side_effect=lambda url, **kwargs: response(MP3 if "/mp3/" in url else HTML))
        self.service = self.make_service()
        self.local: Any = DikiResources(self.root / "local", offline=True)
        self.addCleanup(self.local.close)
        self.api = TestClient(create_app(self.service, run_worker=False))
        self.adapter = ApiAdapter(self.api)
        self.client = RemoteDownloads(URL, TOKEN)
        self.client.session.mount(URL, self.adapter)
        self.addCleanup(self.client.close)

    def make_service(self, **options) -> Any:
        config = Config(
            self.root / "server", TOKEN, require_mount=False, min_free_bytes=0, **options
        )
        service = DownloadService(config, clock=self.clock, sleep=self.clock.sleep, get=self.get)
        self.addCleanup(service.close)
        return service

    def ready(self, word="take", *, need_audio=True):
        self.service.submit([{"word": word, "need_audio": need_audio}])
        self.service.run_cycle()
        self.assertEqual(self.service.status()["jobs"].get("ready"), 1)

    def test_alias_transfer_seeds_local_headword_without_retaining_server_copies(self):
        content = (Path(__file__).parent / "diki_cases" / "lead-astray.html").read_bytes()
        self.get.side_effect = lambda url, **kwargs: response(MP3 if "/mp3/" in url else content)
        self.ready("lead astray")
        self.assertIsNone(self.service.resources._cached("lead somebody astray", "html"))
        self.client.pull(self.local)
        self.assertEqual(self.local.fetch_html("lead somebody astray").encode(), content)
        self.assertEqual(self.local.fetch_audio("lead somebody astray"), MP3)
        with self.service.resources.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM resources").fetchone()[0], 0)
        self.assertEqual(self.get.call_count, 2)

    def test_case_distinct_jobs_keep_separate_audio_and_delivery_records(self):
        from tests.test_diki_headwords import POLISH

        self.get.side_effect = lambda url, **kwargs: response(
            (MP3 + url.encode()) if "/mp3/" in url else POLISH.encode()
        )
        self.assertEqual(self.client.submit(["Polish", "polish"], self.local)["queued"], 2)
        self.service.run_cycle()
        self.assertEqual(self.client.pull(self.local)["wordsImported"], 2)
        self.assertNotEqual(self.local.fetch_audio("Polish"), self.local.fetch_audio("polish"))
        self.assertEqual(self.service.status()["jobs"], {"delivered": 2})
        self.assertEqual(self.get.call_count, 4)

    def test_current_recognized_nonentry_pages_transfer_without_audio(self):
        for name in ("collocation", "reverse", "related"):
            content = (Path(__file__).parent / "diki_cases" / f"page-{name}.html").read_bytes()
            self.get.side_effect = lambda url, content=content, **kwargs: response(content)
            self.service.submit([{"word": name}])
            self.service.run_cycle()
            self.assertEqual(self.client.pull(self.local)["wordsImported"], 1)
            self.assertEqual(self.local.fetch_html(name).encode(), content)
        self.assertEqual(self.get.call_count, 3)

    def test_old_alias_metadata_is_reparsed_for_audio_only_submission(self):
        content = (Path(__file__).parent / "diki_cases" / "lead-astray.html").read_bytes()
        self.local._save("lead astray", "html", content, 200, "fixture", False)
        self.get.side_effect = lambda url, **kwargs: response(MP3)
        result = self.client.submit(["lead astray"], self.local)
        self.assertEqual(result["audioOnly"], 1)
        self.service.run_cycle()
        self.client.pull(self.local)
        self.assertEqual(self.local.fetch_audio("lead somebody astray"), MP3)
        self.assertEqual(self.get.call_count, 1)

    def test_end_to_end_import_then_ack_deletes_server_files_and_keeps_tombstone(self):
        self.ready()
        server_path = self.service.resources.path("take", "html")
        self.assertTrue(server_path.exists())
        result = self.client.pull(self.local)
        self.assertEqual(
            result, {"transfersAcknowledged": 1, "wordsImported": 1, "serverCleanupPending": 0}
        )
        self.assertEqual(self.local.fetch_html("take").encode(), HTML)
        self.assertEqual(self.local.fetch_audio("take"), MP3)
        self.assertFalse(server_path.exists())
        self.assertFalse(self.service.resources.path("take", "audio").exists())
        self.assertIsNone(self.service.resources.metadata("take", "html"))
        self.assertEqual(self.service.status()["jobs"], {"delivered": 1})
        self.assertEqual(
            self.service.submit([{"word": " take "}]), {"queued": 0, "alreadyKnown": 1}
        )
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 2)

    def test_lost_ack_response_resumes_locally_without_fetching_server_payloads_again(self):
        self.ready()
        self.adapter.fail_ack_once = True
        with self.assertRaises(RemoteError):
            self.client.pull(self.local)
        self.assertEqual(self.service.status()["jobs"], {"delivered": 1})
        self.assertFalse(self.service.resources.path("take", "html").exists())
        blobs_before = sum("/files/" in path for _, path in self.adapter.calls)
        result = self.client.pull(self.local)
        self.assertEqual(result["transfersAcknowledged"], 1)
        self.assertEqual(sum("/files/" in path for _, path in self.adapter.calls), blobs_before)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_interrupted_download_keeps_server_data_and_reuses_staged_html(self):
        self.ready()
        self.adapter.fail_blob_once = "/audio"
        with self.assertRaises(RemoteError):
            self.client.pull(self.local)
        self.assertTrue(self.service.resources.path("take", "html").exists())
        self.assertTrue(self.service.resources.path("take", "audio").exists())
        self.assertFalse(any(path.endswith("/ack") for _, path in self.adapter.calls))
        self.assertIsNone(self.local._cached("take", "html"))  # validate entire batch first
        self.client.pull(self.local)
        html_downloads = [
            path for _, path in self.adapter.calls if "/files/" in path and path.endswith("/html")
        ]
        self.assertEqual(len(html_downloads), 1)
        self.assertEqual(self.get.call_count, 2)

    def test_bad_checksum_never_imports_or_acknowledges(self):
        self.ready()
        self.adapter.corrupt_blob_once = True
        with self.assertRaisesRegex(RemoteError, "checksum"):
            self.client.pull(self.local)
        self.assertIsNone(self.local._cached("take", "html"))
        self.assertFalse(any(path.endswith("/ack") for _, path in self.adapter.calls))
        self.assertEqual(self.service.status()["jobs"], {"ready": 1})
        self.client.pull(self.local)
        self.assertTrue(self.local.fetch_audio("take"))

    def test_failed_local_write_preserves_server_and_is_resumable(self):
        self.ready()
        real_save = self.local._save

        def save(word, kind, *args):
            if kind == "audio":
                raise OSError("Disk full")
            return real_save(word, kind, *args)

        with patch.object(self.local, "_save", side_effect=save):
            with self.assertRaisesRegex(RemoteError, "Disk full"):
                self.client.pull(self.local)
        self.assertEqual(self.service.status()["jobs"], {"ready": 1})
        self.assertFalse(any(path.endswith("/ack") for _, path in self.adapter.calls))
        self.assertTrue(self.local.fetch_html("take"))
        self.client.pull(self.local)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_manifest_path_traversal_even_with_matching_manifest_hash_is_rejected(self):
        self.ready()
        self.adapter.tamper_manifest = True
        with self.assertRaisesRegex(RemoteError, "item ID"):
            self.client.pull(self.local)
        self.assertFalse(
            any("/files/" in path or path.endswith("/ack") for _, path in self.adapter.calls)
        )
        self.assertEqual(self.service.status()["jobs"], {"ready": 1})

    def test_wrong_ack_digest_cannot_delete_files(self):
        self.ready()
        transfer = self.service.next_transfer()
        result = self.api.post(
            f"/v1/transfers/{transfer['manifest']['id']}/ack",
            headers={"Authorization": "Bearer " + TOKEN},
            json={"digest": "0" * 64},
        )
        self.assertEqual(result.status_code, 409)
        self.assertTrue(self.service.resources.path("take", "audio").exists())

    def test_pending_manifest_is_stable_across_server_restart(self):
        self.ready()
        envelope = self.service.next_transfer()
        self.service.close()
        other = self.make_service()
        self.assertEqual(other.next_transfer(), envelope)
        self.assertEqual(self.get.call_count, 2)

    def test_old_duplicate_ack_cannot_delete_an_explicit_new_download(self):
        self.ready()
        old = self.service.next_transfer()
        self.client.pull(self.local)
        self.service.submit([{"word": "take"}], redownload=True)
        self.service.run_cycle()
        new = self.service.next_transfer()
        self.assertNotEqual(old["manifest"]["items"][0]["id"], new["manifest"]["items"][0]["id"])
        self.service.acknowledge(old["manifest"]["id"], old["digest"])
        self.assertTrue(self.service.resources.path("take", "audio").exists())
        self.assertEqual(self.service.status()["jobs"], {"ready": 1})

    def test_no_audio_negative_is_transferred_without_guess_requests(self):
        content = (Path(__file__).parent / "diki_cases" / "audio-revenant.html").read_bytes()
        self.get.side_effect = lambda *args, **kwargs: response(content)
        self.ready("revenant")
        self.assertEqual(self.get.call_count, 1)
        self.client.pull(self.local)
        self.assertEqual(self.local.metadata("revenant", "audio")["state"], "no_audio")
        self.assertTrue(self.local.fetch_html("revenant"))

    def test_suggestion_only_html_is_a_complete_transfer_without_mp3(self):
        self.get.side_effect = lambda *args, **kwargs: response(SUGGESTIONS, 404)
        self.ready("tkae")
        self.client.pull(self.local)
        self.assertEqual(self.local.metadata("tkae", "html")["status"], 404)
        self.assertEqual(self.local.metadata("tkae", "html")["exact_match"], 0)
        self.assertEqual(self.get.call_count, 1)

    def test_cached_html_is_parsed_locally_and_only_mp3_crosses_server(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        result = self.client.submit(["take", "take"], self.local)
        self.assertEqual(result["queued"], 1)
        self.assertEqual(result["audioOnly"], 1)
        body = self.adapter.job_bodies[0]
        self.assertNotIn("html", body["items"][0])
        self.assertLess(len(json.dumps(body)), 4096)
        self.assertEqual(
            body["items"][0]["audio_plan"]["urls"], discover_audio_urls(HTML.decode(), "take")
        )
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 1)
        self.assertIn("/mp3/", self.get.call_args.args[0])
        self.assertIsNone(self.service.resources.metadata("take", "html"))
        self.assertFalse(self.service.resources.path("take", "html").exists())
        manifest = self.service.next_transfer()["manifest"]
        self.assertEqual([r["kind"] for r in manifest["items"][0]["resources"]], ["audio"])
        self.client.pull(self.local)
        self.assertEqual(self.adapter.blob_bytes, len(MP3))
        self.assertFalse(any(path.endswith("/html") for _, path in self.adapter.calls))
        self.assertFalse(self.service.resources.path("take", "audio").exists())
        self.assertEqual(self.local.fetch_html("take").encode(), HTML)
        calls = len(self.adapter.calls)
        result = self.client.submit(["take"], self.local)
        self.assertEqual(result["alreadyCached"], 1)
        self.assertEqual(len(self.adapter.calls), calls)

    def test_large_cached_html_never_uploads_or_refetches_html(self):
        content = HTML + b" " * (600 * 1024)
        self.local._save("take", "html", content, 200, "fixture", True)
        self.client.submit(["take"], self.local)
        self.assertNotIn("html", self.adapter.job_bodies[0]["items"][0])
        self.service.run_cycle()
        self.client.pull(self.local)
        self.assertEqual(self.get.call_count, 1)
        self.assertEqual(self.adapter.blob_bytes, len(MP3))
        self.assertEqual(self.local.fetch_html("take").encode(), content)

    def test_no_advertised_audio_is_recorded_locally_without_any_server_call(self):
        content = (Path(__file__).parent / "diki_cases" / "audio-revenant.html").read_bytes()
        self.local._save("revenant", "html", content, 200, "fixture", True)
        result = self.client.submit(["revenant"], self.local)
        self.assertEqual(result["noAudioLocal"], 1)
        self.assertEqual(result["queued"], 0)
        self.assertEqual(self.adapter.calls, [])
        self.get.assert_not_called()
        self.assertEqual(self.local.metadata("revenant", "audio")["state"], "no_audio")
        with DikiResources(self.local.root, offline=True) as reopened:
            self.assertEqual((reopened.metadata("revenant", "audio") or {})["state"], "no_audio")
            self.assertEqual(self.client.submit(["revenant"], reopened)["alreadyCached"], 1)
        self.assertEqual(self.adapter.calls, [])

    def test_no_advertised_audio_can_replace_corrupt_local_audio_metadata(self):
        content = HTML.replace(b"data-audio-url=", b"data-unused-url=")
        self.local._save("take", "html", content, 200, "fixture", True)
        self.local._save("take", "audio", MP3, 200, "fixture")
        self.local.path("take", "audio").write_bytes(b"corrupt")
        self.assertEqual(self.client.submit(["take"], self.local)["noAudioLocal"], 1)
        self.assertEqual(self.local.metadata("take", "audio")["state"], "no_audio")
        self.assertEqual(self.adapter.calls, [])

    def test_local_negative_result_is_invalidated_when_html_changes(self):
        content = HTML.replace(b"data-audio-url=", b"data-unused-url=")
        self.local._save("take", "html", content, 200, "fixture", True)
        self.client.submit(["take"], self.local)
        self.assertEqual(self.local.metadata("take", "audio")["state"], "no_audio")
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.assertEqual(self.client.submit(["take"], self.local)["audioOnly"], 1)
        self.service.run_cycle()
        self.client.pull(self.local)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_audio_only_failed_job_requires_explicit_retry_without_html_fallback(self):
        self.service.close()
        self.service = self.make_service(max_attempts=1)
        self.adapter.api = TestClient(create_app(self.service, run_worker=False))
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.client.submit(["take"], self.local)
        self.get.side_effect = requests.ReadTimeout("stalled MP3")
        self.service.run_cycle()
        self.assertEqual(self.service.status()["jobs"], {"failed": 1})
        self.assertEqual(self.client.submit(["take"], self.local)["alreadyKnown"], 1)
        self.assertEqual(self.get.call_count, 1)
        self.get.side_effect = lambda *a, **kw: response(MP3)
        self.assertEqual(self.client.submit(["take"], self.local, retry_failed=True)["queued"], 1)
        self.service.run_cycle()
        self.client.pull(self.local)
        self.assertEqual(self.get.call_count, 2)
        self.assertTrue(all("/mp3/" in call.args[0] for call in self.get.call_args_list))
        self.assertIsNone(self.service.resources.metadata("take", "html"))

    def test_audio_only_challenge_pauses_without_trying_html_or_other_urls(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.client.submit(["take"], self.local)
        self.get.side_effect = lambda *a, **kw: response(b"<title>Just a moment...</title>")
        self.service.run_cycle()
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 1)
        self.assertIn("/mp3/", self.get.call_args.args[0])
        self.assertGreater(self.service.status()["cooldownUntil"], self.clock())

    def test_audio_only_retained_old_audio_cannot_reset_fallback_cursor(self):
        self.service.close()
        self.service = self.make_service(requests_per_day=1)
        self.adapter.api = TestClient(create_app(self.service, run_worker=False))
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.service.resources._save(
            "take", "audio", MP3, 200, "https://www.diki.pl/images-common/en/mp3/old.mp3"
        )
        self.client.submit(["take"], self.local)
        self.get.side_effect = lambda *a, **kw: response(b"missing", 404)
        self.service.run_cycle()
        urls = discover_audio_urls(HTML.decode(), "take")
        self.assertEqual(self.get.call_args.args[0], urls[0])
        self.clock.now = self.service.status()["budgetResetsAt"] + 1
        self.get.side_effect = lambda *a, **kw: response(MP3)
        self.service.run_cycle()
        self.assertEqual(self.get.call_args.args[0], urls[1])
        self.assertEqual(self.get.call_count, 2)
        self.client.pull(self.local)

    def test_outdated_negative_discovery_is_reparsed_locally(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.local._audio_plan("take", HTML)
        with self.local.db() as db:
            db.execute("INSERT INTO resources(word,kind,state) VALUES ('take','audio','no_audio')")
            db.execute("UPDATE audio_discovery SET version=?,exhausted=1", (DISCOVERY_VERSION - 1,))
        self.assertEqual(self.client.submit(["take"], self.local)["audioOnly"], 1)
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 1)

    def test_audio_only_404_fallback_cursor_and_budget_survive_restart(self):
        self.service.close()
        self.service = self.make_service(requests_per_day=1)
        self.adapter.api = TestClient(create_app(self.service, run_worker=False))
        self.local._save("take", "html", HTML, 200, "fixture", True)
        urls = discover_audio_urls(HTML.decode(), "take")
        self.assertGreater(len(urls), 1)
        self.get.side_effect = lambda *a, **kw: response(b"missing", 404)
        self.client.submit(["take"], self.local)
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 1)
        self.assertEqual(self.get.call_args.args[0], urls[0])
        self.assertEqual(self.service.status()["jobs"], {"queued": 1})
        self.service.close()
        self.service = self.make_service(requests_per_day=1)
        self.adapter.api = TestClient(create_app(self.service, run_worker=False))
        self.assertEqual(self.client.submit(["take"], self.local)["alreadyKnown"], 1)
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 1)
        self.clock.now = self.service.status()["budgetResetsAt"] + 1
        self.get.side_effect = lambda *a, **kw: response(MP3)
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.get.call_args.args[0], urls[1])
        self.client.pull(self.local)
        self.assertEqual(self.adapter.blob_bytes, len(MP3))
        self.assertIsNone(self.service.resources.metadata("take", "html"))

    def test_audio_only_all_404s_transfer_a_negative_receipt_without_payloads(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        urls = discover_audio_urls(HTML.decode(), "take")
        self.get.side_effect = lambda *a, **kw: response(b"missing", 404)
        self.client.submit(["take"], self.local)
        self.service.run_cycle()
        envelope = self.service.next_transfer()
        self.assertEqual(envelope["manifest"]["items"][0]["resources"], [])
        self.assertEqual(envelope["manifest"]["items"][0]["audioState"], "no_audio")
        self.assertEqual(self.get.call_count, len(urls))
        self.service.close()
        self.service = self.make_service()
        self.adapter.api = TestClient(create_app(self.service, run_worker=False))
        self.assertEqual(self.service.next_transfer(), envelope)
        self.service.run_cycle()
        self.client.pull(self.local)
        self.assertEqual(self.adapter.blob_bytes, 0)
        self.assertFalse(any("/files/" in path for _, path in self.adapter.calls))
        self.assertEqual(self.local.metadata("take", "audio")["state"], "no_audio")
        self.assertEqual(self.client.submit(["take"], self.local)["alreadyCached"], 1)
        self.assertEqual(self.get.call_count, len(urls))

    def test_audio_only_lost_ack_reuses_local_payload(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.client.submit(["take"], self.local)
        self.service.run_cycle()
        self.adapter.fail_ack_once = True
        with self.assertRaises(RemoteError):
            self.client.pull(self.local)
        self.assertEqual(self.service.status()["jobs"], {"delivered": 1})
        self.assertEqual(self.client.pull(self.local)["wordsImported"], 1)
        self.assertEqual(self.adapter.blob_bytes, len(MP3))
        self.assertEqual(self.get.call_count, 1)

    def test_audio_only_interrupted_transfer_retains_server_and_resumes(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.client.submit(["take"], self.local)
        self.service.run_cycle()
        self.adapter.fail_blob_once = "/audio"
        with self.assertRaises(RemoteError):
            self.client.pull(self.local)
        self.assertTrue(self.service.resources.path("take", "audio").exists())
        self.assertFalse(any(path.endswith("/ack") for _, path in self.adapter.calls))
        self.client.pull(self.local)
        self.assertEqual(self.get.call_count, 1)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_audio_only_local_write_failure_reuses_staging_without_redownload(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.client.submit(["take"], self.local)
        self.service.run_cycle()
        with patch.object(self.local, "_save", side_effect=OSError("Disk full")):
            with self.assertRaisesRegex(RemoteError, "Disk full"):
                self.client.pull(self.local)
        self.assertTrue(self.service.resources.path("take", "audio").exists())
        self.client.pull(self.local)
        self.assertEqual(self.adapter.blob_bytes, len(MP3))
        self.assertEqual(self.get.call_count, 1)

    def test_audio_only_negative_write_failure_does_not_ack(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.get.side_effect = lambda *a, **kw: response(b"missing", 404)
        self.client.submit(["take"], self.local)
        self.service.run_cycle()
        with patch.object(self.client, "_record_no_audio", side_effect=OSError("Disk full")):
            with self.assertRaisesRegex(RemoteError, "Disk full"):
                self.client.pull(self.local)
        self.assertFalse(any(path.endswith("/ack") for _, path in self.adapter.calls))
        self.assertEqual(self.service.status()["jobs"], {"ready": 1})
        self.client.pull(self.local)
        self.assertEqual(self.local.metadata("take", "audio")["state"], "no_audio")

    def test_audio_only_changed_or_missing_html_blocks_before_mp3_download(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.client.submit(["take"], self.local)
        self.service.run_cycle()
        for content in (SUGGESTIONS, None):
            if content is None:
                self.local.path("take", "html").unlink()
            else:
                self.local._save("take", "html", content, 200, "fixture")
            with self.assertRaisesRegex(RemoteError, "original local HTML"):
                self.client.pull(self.local)
        self.assertEqual(self.adapter.blob_bytes, 0)
        self.assertFalse(any(path.endswith("/ack") for _, path in self.adapter.calls))
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.client.pull(self.local)
        self.assertEqual(self.get.call_count, 1)

    def test_mixed_audio_only_and_html_jobs_import_as_one_batch(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.get.side_effect = lambda url, **kw: (
            response(MP3) if "/mp3/" in url else response(SUGGESTIONS, 404)
        )
        self.client.submit(["take", "tkae"], self.local)
        self.service.run_cycle()
        self.assertEqual(len(self.service.next_transfer()["manifest"]["items"]), 2)
        self.assertEqual(self.client.pull(self.local)["wordsImported"], 2)
        self.assertEqual(self.adapter.blob_bytes, len(MP3) + len(SUGGESTIONS))
        self.assertEqual(self.local.fetch_html("take").encode(), HTML)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_audio_only_rejects_unsafe_or_malformed_jobs_without_requests(self):
        plan = {
            "htmlDigest": hashlib.sha256(HTML).hexdigest(),
            "discoveryVersion": DISCOVERY_VERSION,
            "urls": discover_audio_urls(HTML.decode(), "take"),
        }
        bad_plans = [
            dict(plan, urls=[url])
            for url in (
                "http://127.0.0.1/internal.mp3",
                "https://example.com/recording.mp3",
                "https://www.diki.pl/slownik-angielskiego?q=take",
                "/images-common/en/mp3/take.mp3",
                "https://www.diki.pl/images-common/en/mp3/../take.mp3",
            )
        ]
        bad_plans += [
            dict(plan, urls=[]),
            dict(plan, urls=plan["urls"] * 2),
            dict(plan, htmlDigest="bad"),
            dict(plan, discoveryVersion=DISCOVERY_VERSION + 1),
        ]
        items = [{"word": "take", "audio_plan": bad} for bad in bad_plans]
        items += [
            {"word": "take", "audio_plan": plan, "need_audio": False},
            {"word": "take", "audio_plan": plan, "html": "anything"},
        ]
        for item in items:
            with self.subTest(item=item):
                result = self.api.post(
                    "/v1/jobs", headers={"Authorization": "Bearer " + TOKEN}, json={"items": [item]}
                )
                self.assertEqual(result.status_code, 422)
        self.assertEqual(self.service.status()["jobs"], {})
        self.get.assert_not_called()

    def test_audio_only_manifest_cannot_inject_other_audio_or_bypass_html_context(self):
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.client.submit(["take"], self.local)
        self.service.run_cycle()
        envelope = self.service.next_transfer()
        malformed = copy.deepcopy(envelope)
        malformed["manifest"]["items"][0]["resources"][0]["source"] = (
            "https://www.diki.pl/images-common/en/mp3/other.mp3"
        )
        malformed["digest"] = digest(malformed["manifest"])
        with self.assertRaisesRegex(ValueError, "audio-only plan"):
            validate_manifest(malformed)
        malformed["manifest"]["items"][0]["audioPlan"]["urls"] = [
            "https://www.diki.pl/images-common/en/mp3/other.mp3"
        ]
        malformed["digest"] = digest(malformed["manifest"])
        with patch.object(self.client, "_json", return_value=malformed):
            with self.assertRaisesRegex(RemoteError, "locally discovered"):
                self.client.pull(self.local)
        self.assertEqual(self.adapter.blob_bytes, 0)

    def test_existing_queue_schema_and_protocol1_outbox_migrate_without_refetch(self):
        self.ready()
        envelope = self.service.next_transfer()
        envelope["manifest"]["protocol"] = 1
        envelope["digest"] = digest(envelope["manifest"])
        with self.service.resources.db() as db:
            db.execute("UPDATE remote_batches SET envelope=?", (json.dumps(envelope),))
            db.execute("ALTER TABLE remote_jobs DROP COLUMN audio_plan")
        self.service.close()
        self.service = self.make_service()
        self.adapter.api = TestClient(create_app(self.service, run_worker=False))
        self.assertEqual(self.service.next_transfer(), envelope)
        self.client.pull(self.local)
        self.assertEqual(self.get.call_count, 2)

    def test_large_audio_plans_are_split_before_manifest_json_limit(self):
        urls = [
            "https://www.diki.pl/images-common/en/mp3/" + "x" * 1800 + str(index) + ".mp3"
            for index in range(32)
        ]
        plan = {
            "htmlDigest": hashlib.sha256(HTML).hexdigest(),
            "discoveryVersion": DISCOVERY_VERSION,
            "urls": urls,
        }
        self.service.submit([{"word": f"word{index}", "audio_plan": plan} for index in range(10)])
        self.get.side_effect = lambda *a, **kw: response(MP3)
        for _ in range(5):
            self.clock.now += 1000
            self.service.run_cycle()
        self.assertEqual(self.service.status()["jobs"], {"ready": 10})
        envelope = self.service.next_transfer()
        self.assertLess(len(envelope["manifest"]["items"]), 10)
        self.assertLessEqual(len(canonical(envelope)), MAX_MANIFEST_BYTES)
        validate_manifest(envelope)

    def test_existing_local_mp3_does_not_get_downloaded_again_on_server(self):
        self.local._save(
            "take", "audio", MP3, 200, "https://www.diki.pl/images-common/en/mp3/take.mp3"
        )
        self.client.submit(["take"], self.local)
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 1)
        self.assertNotIn("/mp3/", self.get.call_args.args[0])
        self.client.pull(self.local)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_requests_budget_including_partial_word_survives_restart_and_resets_next_utc_day(self):
        self.service.close()
        self.service = self.make_service(requests_per_day=1)
        self.service.submit([{"word": "take"}])
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 1)
        self.assertEqual(self.service.status()["requestsToday"], 1)
        self.assertEqual(self.service.status()["jobs"], {"queued": 1})
        self.assertTrue(self.service.resources.path("take", "html").exists())
        self.service.close()
        self.service = self.make_service(requests_per_day=1)
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 1)
        self.clock.now = self.service.status()["budgetResetsAt"] + 1
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 2)
        self.assertIn("/mp3/", self.get.call_args.args[0])
        self.assertEqual(self.service.status()["jobs"], {"ready": 1})
        self.assertEqual(self.service.status()["requestsToday"], 1)

    def test_challenge_consumes_one_attempt_and_stops_fresh_words_across_cycles(self):
        self.get.side_effect = lambda *args, **kwargs: response(b"<title>Just a moment...</title>")
        self.service.submit([{"word": "one"}, {"word": "two"}])
        self.service.run_cycle()
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 1)
        self.assertEqual(self.service.status()["requestsToday"], 1)
        self.assertGreater(self.service.status()["cooldownUntil"], self.clock())

    def test_timeouts_count_against_budget_and_three_failures_back_off_globally(self):
        self.get.side_effect = requests.ReadTimeout("slow origin")
        self.service.submit([{"word": word} for word in ["one", "two", "three", "four"]])
        self.service.run_cycle()
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 3)
        self.assertEqual(self.service.status()["requestsToday"], 3)
        self.assertGreater(self.service.status()["cooldownUntil"], self.clock())

    def test_runtime_budget_exhaustion_and_storage_pressure_cause_no_http_requests(self):
        self.service.submit([{"word": "take"}])
        day, _ = self.service._day()
        with self.service.resources.db() as db:
            db.execute(
                "INSERT INTO remote_usage(day,work_seconds) VALUES (?,?)",
                (day, self.service.config.work_seconds_per_day),
            )
        self.service.run_cycle()
        self.get.assert_not_called()
        with self.service.resources.db() as db:
            db.execute("UPDATE remote_usage SET work_seconds=0")
        usage = type("Disk", (), {"free": 0})()
        with patch("deploy.northflank.service.shutil.disk_usage", return_value=usage):
            self.service.run_cycle()
        self.get.assert_not_called()
        self.assertEqual(self.service.status()["jobs"], {"queued": 1})

    def test_runtime_refund_uses_monotonic_elapsed_time(self):
        self.service.submit([{"word": "take"}])
        with patch.object(self.service, "monotonic", side_effect=[100, 107]):
            self.service.run_cycle()
        self.assertEqual(self.service.status()["workSecondsToday"], 7)

    def test_unexpected_exception_does_not_leave_job_running_or_hot_retry(self):
        self.service.submit([{"word": "take"}])
        with patch.object(self.service, "_ready", side_effect=RuntimeError("unexpected")):
            with self.assertRaises(RuntimeError):
                self.service.run_cycle()
        self.assertEqual(self.service.status()["jobs"], {"queued": 1})
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 2)

    def test_start_recovers_running_job_but_never_starts_duplicate_worker(self):
        self.service.submit([{"word": "take"}])
        with self.service.resources.db() as db:
            db.execute("UPDATE remote_jobs SET state='running'")
        with patch.object(self.service, "_loop"):
            self.service.start()
            self.service.thread.join(timeout=1)
        self.assertEqual(self.service.status()["jobs"], {"queued": 1})
        other = self.make_service()
        with self.assertRaises(BlockingIOError):
            other.start()

    def test_ack_cleanup_failure_is_retried_without_redownloading(self):
        self.ready()
        envelope = self.service.next_transfer()
        path = self.service.resources.path("take", "html")
        real_unlink = Path.unlink

        def unlink(value, *args, **kwargs):
            if value == path:
                raise OSError("Temporary volume failure")
            return real_unlink(value, *args, **kwargs)

        with (
            patch.object(Path, "unlink", unlink),
            self.assertLogs("deploy.northflank.service", "ERROR"),
        ):
            result = self.service.acknowledge(envelope["manifest"]["id"], envelope["digest"])
        self.assertEqual(result["cleanupPending"], 1)
        self.service.run_cycle()
        self.assertFalse(path.exists())
        self.assertEqual(self.get.call_count, 2)

    def test_damaged_server_payload_is_not_silently_redownloaded_or_deleted(self):
        self.ready()
        envelope = self.service.next_transfer()
        path = self.service.resources.path("take", "html")
        path.write_bytes(b"corrupt")
        with self.assertRaises(RemoteError):
            self.client.pull(self.local)
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.service.next_transfer(), envelope)
        self.assertTrue(path.exists())

    def test_corrupt_pending_manifest_is_reported_without_fetching_or_deleting(self):
        self.ready()
        envelope = self.service.next_transfer()
        with self.service.resources.db() as db:
            db.execute("UPDATE remote_batches SET envelope='{}'")
        result = self.api.get("/v1/transfers/next", headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(result.status_code, 409)
        self.assertIn("no automatic redownload", result.json()["detail"])
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 2)
        self.assertTrue(self.service.resources.path("take", "html").exists())
        # Restoring the exact envelope is sufficient; no new generation is needed.
        with self.service.resources.db() as db:
            db.execute("UPDATE remote_batches SET envelope=?", (json.dumps(envelope),))
        self.client.pull(self.local)

    def test_failed_job_requires_explicit_retry_and_reuses_completed_html(self):
        self.service.close()
        self.service = self.make_service(max_attempts=1)
        self.api = TestClient(create_app(self.service, run_worker=False))
        self.adapter.api = self.api
        self.get.side_effect = lambda url, **kwargs: (
            response(HTML)
            if "/mp3/" not in url
            else (_ for _ in ()).throw(requests.ReadTimeout("stall"))
        )
        self.client.submit(["take"], self.local)
        self.service.run_cycle()
        self.assertEqual(self.service.status()["jobs"], {"failed": 1})
        self.assertEqual(self.client.submit(["take"], self.local)["alreadyKnown"], 1)
        self.clock.now += 100000
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 2)
        self.get.side_effect = lambda url, **kwargs: response(MP3)
        self.assertEqual(self.client.submit(["take"], self.local, retry_failed=True)["queued"], 1)
        self.service.run_cycle()
        self.assertEqual(self.get.call_count, 3)
        self.assertIn("/mp3/", self.get.call_args.args[0])
        self.client.pull(self.local)

    def test_repeated_sigkill_reserves_budgets_and_eventually_fails_job(self):
        self.service.submit([{"word": "take"}])
        self.service.close()
        # Kill real child processes inside the HTTP callback, after reservations
        # and the running state commit, so no Python finally block can recover it.
        script = """
import os, signal, sys
from pathlib import Path
from unittest.mock import patch
from deploy.northflank.config import Config
from deploy.northflank.service import DownloadService
from tests.test_diki_resources import Clock
clock = Clock()
clock.now = int(sys.argv[2])
service = DownloadService(Config(Path(sys.argv[1]), sys.argv[3], require_mount=False,
    min_free_bytes=0, max_attempts=3), clock=clock, sleep=clock.sleep,
    get=lambda *a, **kw: os.kill(os.getpid(), signal.SIGKILL))
with patch.object(service, '_loop'):
    service.start()
    service.thread.join()
clock.now += 301
service.run_cycle()
"""
        for index in range(3):
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(self.root / "server"),
                    str(1000 + index * 1000),
                    TOKEN,
                ],
                capture_output=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr.decode())
        self.clock.now = 5000
        self.service = self.make_service(max_attempts=3)
        with patch.object(self.service, "_loop"):
            self.service.start()
            self.service.thread.join(timeout=1)
        status = self.service.status()
        self.assertEqual(status["jobs"], {"failed": 1})
        self.assertEqual(status["failedWords"][0]["attempts"], 3)
        self.assertEqual(status["requestsToday"], 3)
        self.assertEqual(status["workSecondsToday"], 3 * self.service.config.batch_seconds)
        self.service.run_cycle()
        self.get.assert_not_called()

    def test_ack_database_commit_failure_prevents_any_deletion(self):
        self.ready()
        envelope = self.service.next_transfer()
        real_db = self.service.resources.db

        @contextmanager
        def failed_commit():
            with real_db() as db:
                yield db
                raise sqlite3.OperationalError("Commit failed")

        with patch.object(self.service.resources, "db", failed_commit):
            with self.assertRaises(sqlite3.OperationalError):
                self.service.acknowledge(envelope["manifest"]["id"], envelope["digest"])
        self.assertEqual(self.service.next_transfer(), envelope)
        self.assertEqual(self.service.status()["jobs"], {"ready": 1})
        self.assertTrue(self.service.resources.path("take", "audio").exists())

    def test_server_unlinks_only_after_import_and_receipt_commit(self):
        self.ready()
        paths = {self.service.resources.path("take", kind) for kind in ("html", "audio")}
        real_unlink = Path.unlink
        deleted = []

        def unlink(path, *args, **kwargs):
            if path in paths:
                with self.service.resources.db() as db:
                    self.assertEqual(
                        db.execute("SELECT acknowledged FROM remote_batches").fetchone()[0], 1
                    )
                    self.assertEqual(
                        db.execute("SELECT state FROM remote_jobs").fetchone()[0], "delivered"
                    )
                self.assertEqual(self.local.fetch_audio("take"), MP3)
                self.assertEqual(self.local.fetch_html("take").encode(), HTML)
                deleted.append(path)
            return real_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", unlink):
            self.client.pull(self.local)
        self.assertEqual(set(deleted), paths)

    def test_cleanup_directory_fsync_failure_keeps_receipt_and_retries_after_restart(self):
        self.ready()
        envelope = self.service.next_transfer()
        with patch("deploy.northflank.service.os.fsync", side_effect=OSError("fsync failed")):
            with self.assertLogs("deploy.northflank.service", "ERROR"):
                result = self.service.acknowledge(envelope["manifest"]["id"], envelope["digest"])
        self.assertEqual(result["cleanupPending"], 1)
        self.service.close()
        self.service = self.make_service()
        result = self.service.acknowledge(envelope["manifest"]["id"], envelope["digest"])
        self.assertEqual(result["cleanupPending"], 0)
        self.assertFalse(self.service.resources.path("take", "audio").exists())
        self.assertEqual(self.get.call_count, 2)

    def test_local_directory_fsync_failure_never_acknowledges(self):
        self.ready()
        real_fsync = os.fsync
        local_html = self.local.root / "html"
        directory_inode = local_html.stat().st_ino

        def fsync(descriptor):
            info = os.fstat(descriptor)
            if stat.S_ISDIR(info.st_mode) and info.st_ino == directory_inode:
                raise OSError("Local cache directory fsync failed")
            return real_fsync(descriptor)

        with patch("external_apis.diki_resources.os.fsync", side_effect=fsync):
            with self.assertRaisesRegex(RemoteError, "directory fsync failed"):
                self.client.pull(self.local)
        self.assertFalse(any(path.endswith("/ack") for _, path in self.adapter.calls))
        self.assertEqual(self.service.status()["jobs"], {"ready": 1})
        self.client.pull(self.local)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_cache_is_revalidated_after_import_before_ack(self):
        self.ready()
        real_import = self.client._import

        def damage(item, contents, resources):
            real_import(item, contents, resources)
            resources.path(item["word"], "audio").write_bytes(b"damaged after import")

        with patch.object(self.client, "_import", side_effect=damage):
            with self.assertRaisesRegex(RemoteError, "durably available"):
                self.client.pull(self.local)
        self.assertFalse(any(path.endswith("/ack") for _, path in self.adapter.calls))
        self.client.pull(self.local)
        self.assertEqual(self.local.fetch_audio("take"), MP3)

    def test_auth_health_and_polling_never_trigger_downloads(self):
        self.assertEqual(self.api.get("/health").status_code, 200)
        self.assertEqual(self.api.get("/v1/status").status_code, 401)
        self.assertEqual(
            self.api.post("/v1/jobs", json={"items": [{"word": "take"}]}).status_code, 401
        )
        self.assertEqual((self.client.status() or {})["jobs"], {})
        self.assertEqual(self.client.pull(self.local)["wordsImported"], 0)
        self.get.assert_not_called()

    def test_oversized_authenticated_request_is_rejected(self):
        result = self.api.post(
            "/v1/jobs",
            headers={"Authorization": "Bearer " + TOKEN},
            content=b" " * (2 * 1024 * 1024 + 1),
        )
        self.assertEqual(result.status_code, 413)
        self.assertEqual(self.service.status()["jobs"], {})

    def test_configuration_fails_closed_without_a_persistent_mount(self):
        with self.assertRaisesRegex(ValueError, "persistent volume"):
            Config(self.root / "unmounted", TOKEN).validate()
        with self.assertRaisesRegex(ValueError, "absolute"):
            Config(Path("relative"), TOKEN, require_mount=False).validate()

    def test_plain_http_is_only_allowed_for_local_testing(self):
        with self.assertRaises(RemoteError):
            RemoteDownloads("http://remote.example", TOKEN)
        local = RemoteDownloads("http://127.0.0.1:8080", TOKEN)
        local.close()

    def test_unusable_runtime_limits_and_non_ascii_tokens_are_rejected(self):
        for option in ({"batch_seconds": 15}, {"work_seconds_per_day": 10}):
            with self.assertRaisesRegex(ValueError, "request allowance"):
                Config(self.root / "server", TOKEN, require_mount=False, **option).validate()
        with self.assertRaises(RemoteError):
            RemoteDownloads(URL, "\u0105" * 40)
        with self.assertRaises(ValueError):
            Config(self.root / "server", "\u0105" * 40, require_mount=False).validate()


@skipUnless(os.getenv("RUN_LOOPBACK_TESTS") == "1", "Explicit loopback transport check")
class TestBoundedHTTPStreaming(TestCase):
    """Exercise requests/urllib3 read1 over real loopback HTTP sockets."""

    def setUp(self):
        self.release = threading.Event()
        release = self.release

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                if self.path == "/gzip":
                    body = gzip.compress(HTML)
                    self.send_header("Content-Encoding", "gzip")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    for offset in range(0, len(body), 17):
                        chunk = body[offset : offset + 17]
                        self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                    self.wfile.write(b"0\r\n\r\n")
                    return
                self.send_header(
                    "Content-Length", str(len(HTML) + (10 if self.path == "/short" else 0))
                )
                self.end_headers()
                try:
                    if self.path == "/short":
                        self.wfile.write(HTML)
                        return
                    if self.path == "/trickle":
                        self.wfile.write(HTML[:1])
                        self.wfile.flush()
                    release.wait(3)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.session = requests.Session()
        self.session.trust_env = False
        self.addCleanup(self.session.close)

    def close_server(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def stream(self, path, read_timeout: float = 1):
        response = self.session.get(
            f"http://127.0.0.1:{self.server.server_port}{path}",
            stream=True,
            timeout=(1, read_timeout),
        )
        bounded = BoundedResponse(response, threading.Event(), time.monotonic() + 10)
        self.addCleanup(bounded.close)
        return bounded

    def test_chunked_gzip_body_is_decoded_without_losing_bytes(self):
        self.assertEqual(b"".join(self.stream("/gzip").iter_content(65536)), HTML)

    def test_read1_yields_available_bytes_and_checks_deadline_before_more_reads(self):
        bounded = self.stream("/trickle")
        chunks = bounded.iter_content(65536)
        self.assertEqual(next(chunks), HTML[:1])
        with patch("deploy.northflank.service.time.monotonic", return_value=bounded.deadline + 1):
            with self.assertRaises(DikiTimeout):
                next(chunks)

    def test_stalled_body_becomes_read_timeout(self):
        with self.assertRaises(requests.ReadTimeout):
            list(self.stream("/stall", read_timeout=0.05).iter_content(65536))

    def test_truncated_content_length_is_not_accepted_as_complete(self):
        with self.assertRaises(requests.ReadTimeout):
            list(self.stream("/short").iter_content(65536))
