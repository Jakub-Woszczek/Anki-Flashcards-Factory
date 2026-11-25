"""Ready-page statistics use retained HTML and preserve remote transfer/recovery rules."""

import hashlib
from unittest.mock import patch

from backend.existing_note_coverage import html_coverage
from external_apis.diki_transfer import html_source
from tests.test_diki_page import fixture
from tests.test_diki_resources import HTML, MP3, SUGGESTIONS, response
from tests.test_remote_preparation import RemoteFixture


class TestReadyHtmlStatus(RemoteFixture):
    def test_ready_categories_match_app_statistics_and_status_does_no_html_work(self):
        words = ["entries", "suggestions", "related", "collocation", "not-found", "reverse"]
        for word in words:
            document = fixture(word).encode()
            self.get.side_effect = lambda *args, document=document, **kwargs: response(document)
            self.service.submit([{"word": word, "need_audio": False}])
            self.service.run_cycle()
        self.service.submit([{"word": "not downloaded"}])
        inventory = {"version": 2, "notes": [{"word": word} for word in words]}
        app_report = html_coverage(inventory, self.service.resources, {})
        before_requests = self.get.call_count
        with (
            patch(
                "deploy.northflank.service.inspect_page",
                side_effect=AssertionError("Status must not reparse HTML"),
            ),
            patch.object(
                self.service.resources,
                "_read_cached",
                side_effect=AssertionError("Status must not read cached HTML"),
            ),
        ):
            status = self.client.status()
            self.assertEqual(self.client.status(), status)
        assert status is not None
        self.assertEqual(status["jobs"], {"queued": 1, "ready": len(words)})
        self.assertEqual(status["readyHtml"]["total"], len(words))
        self.assertEqual(
            status["readyHtml"]["categories"],
            {
                item["key"]: item["count"]
                for item in app_report["categories"]
                if item["key"] != "unprocessable"
            },
        )
        self.assertEqual(status["readyHtml"]["categories"]["not_found"], 2)
        self.assertEqual(status["readyAudioOnly"], 0)
        self.assertEqual(self.get.call_count, before_requests)
        with self.service.resources.db() as db:
            stored = db.execute(
                """SELECT j.html_digest,r.digest FROM remote_jobs j
                JOIN resources r ON j.word=r.word AND r.kind='html' WHERE j.state='ready'"""
            ).fetchall()
        self.assertEqual(len(stored), len(words))
        self.assertTrue(all(row[0] == row[1] for row in stored))

    def test_existing_ready_jobs_backfill_once_without_changing_frozen_transfer_or_budgets(self):
        self.ready()
        envelope = self.service.next_transfer()
        before = self.service.status()
        with self.service.resources.db() as db:
            db.execute("ALTER TABLE remote_jobs DROP COLUMN html_kind")
            db.execute("ALTER TABLE remote_jobs DROP COLUMN html_digest")
        self.service.close()
        self.get.side_effect = AssertionError("Migration must not contact Diki")
        self.service = self.make_service()
        status = self.service.status()
        self.assertEqual(status["readyHtml"]["categories"]["entries"], 1)
        self.assertEqual(self.service.next_transfer(), envelope)
        self.assertEqual(self.service.resources.path("take", "html").read_bytes(), HTML)
        self.assertEqual(self.service.resources.path("take", "audio").read_bytes(), MP3)
        for key in ("jobs", "requestsToday", "workSecondsToday", "storedBytes"):
            self.assertEqual(status[key], before[key])
        self.service.close()
        with patch(
            "deploy.northflank.service.inspect_page",
            side_effect=AssertionError("Persisted classifications must survive restart"),
        ):
            self.service = self.make_service()
            self.assertEqual(self.service.status()["readyHtml"], status["readyHtml"])
        # Jobs remain ready while their stable manifest is in flight, until ACK.
        self.service.acknowledge(envelope["manifest"]["id"], envelope["digest"])
        status = self.service.status()
        self.assertEqual(status["jobs"], {"delivered": 1})
        self.assertEqual(status["readyHtml"]["total"], 0)
        self.assertFalse(any(status["readyHtml"]["categories"].values()))

    def test_audio_only_downloads_and_negative_receipts_are_separate_from_html(self):
        status = self.service.status()
        self.assertEqual(status["readyHtml"]["total"], 0)
        self.assertEqual(status["readyAudioOnly"], 0)
        for word, missing_audio in [("take", False), ("other", True)]:
            self.local._save(
                word, "html", HTML.replace(b"take", word.encode()), 200, "fixture", True
            )
            self.get.side_effect = lambda *args, missing=missing_audio, **kwargs: (
                response(b"missing", 404) if missing else response(MP3)
            )
            self.assertEqual(self.client.submit([word], self.local)["audioOnly"], 1)
            self.service.run_cycle()
        status = self.service.status()
        self.assertEqual(status["jobs"], {"ready": 2})
        self.assertEqual(status["readyHtml"]["total"], 0)
        self.assertEqual(status["readyAudioOnly"], 2)
        self.assertFalse(any(status["readyHtml"]["categories"].values()))
        envelope = self.service.next_transfer()
        self.assertEqual([len(item["resources"]) for item in envelope["manifest"]["items"]], [1, 0])
        self.assertEqual(self.service.status()["readyAudioOnly"], 2)
        self.service.acknowledge(envelope["manifest"]["id"], envelope["digest"])
        self.assertEqual(self.service.status()["readyAudioOnly"], 0)

    def test_unbatched_html_promotion_clears_previous_category_for_audio_only_generation(self):
        self.ready(need_audio=False)
        self.local._save("take", "html", HTML, 200, "fixture", True)
        self.assertEqual(self.client.submit(["take"], self.local)["audioOnly"], 1)
        status = self.service.status()
        self.assertEqual(status["jobs"], {"queued": 1})
        self.assertEqual(status["readyHtml"]["total"], 0)
        with self.service.resources.db() as db:
            row = db.execute("SELECT html_kind,html_digest FROM remote_jobs").fetchone()
        self.assertEqual(tuple(row), (None, None))
        self.service.run_cycle()
        status = self.service.status()
        self.assertEqual(status["readyHtml"]["total"], 0)
        self.assertEqual(status["readyAudioOnly"], 1)
        self.assertEqual(self.get.call_count, 2)

    def test_batched_promotion_preserves_old_counts_until_ack_and_reclassifies_followup(self):
        self.ready(need_audio=False)
        envelope = self.service.next_transfer()
        self.service.submit([{"word": "take"}])
        self.assertEqual(self.service.status()["readyHtml"]["total"], 1)
        self.assertEqual(self.service.next_transfer(), envelope)
        self.service.acknowledge(envelope["manifest"]["id"], envelope["digest"])
        self.assertEqual(self.service.status()["readyHtml"]["total"], 0)
        with self.service.resources.db() as db:
            row = db.execute("SELECT html_kind,html_digest FROM remote_jobs").fetchone()
        self.assertEqual(tuple(row), (None, None))
        self.service.run_cycle()
        self.assertEqual(self.service.status()["readyHtml"]["categories"]["entries"], 1)
        self.service.acknowledge(envelope["manifest"]["id"], envelope["digest"])
        self.assertEqual(self.service.status()["readyHtml"]["total"], 1)
        self.assertEqual(self.get.call_count, 2)

    def test_backfill_reports_missing_and_unusable_html_against_frozen_artifact_digest(self):
        words = ["take", "missing", "corrupt", "changed"]
        self.service.submit([{"word": word, "need_audio": False} for word in words])
        self.service.run_cycle()
        self.assertEqual(self.service.status()["jobs"], {"ready": len(words)})
        envelope = self.service.next_transfer()
        self.service.resources.path("missing", "html").unlink()
        self.service.resources.path("corrupt", "html").write_bytes(b"corrupted bytes")
        self.service.resources._save("changed", "html", SUGGESTIONS, 200, html_source("changed"))
        with self.service.resources.db() as db:
            db.execute("UPDATE remote_jobs SET html_kind=NULL,html_digest=NULL")
        self.service.close()
        self.get.side_effect = AssertionError("Backfill must not repair/redownload resources")
        self.service = self.make_service()
        status = self.service.status()
        self.assertEqual(status["readyHtml"]["total"], len(words))
        self.assertEqual(status["readyHtml"]["categories"]["entries"], 1)
        self.assertEqual(status["readyHtml"]["categories"]["missing"], 1)
        self.assertEqual(status["readyHtml"]["categories"]["unusable"], 2)
        self.assertEqual(status["readyHtml"]["categories"]["suggestions"], 0)
        self.assertEqual(self.service.next_transfer(), envelope)
        with self.service.resources.db() as db:
            digests = [row[0] for row in db.execute("SELECT html_digest FROM remote_jobs")]
        self.assertEqual(digests, [hashlib.sha256(HTML).hexdigest()] * len(words))
