import asyncio
import importlib
import json
import tempfile
from pathlib import Path
from typing import Any
from unittest import TestCase
from unittest.mock import Mock, patch

from backend.services import FactoryService
from backend.storage import SessionStore
from backend.word_completion import WordCompletion
from external_apis.diki_resources import NoAudio
from tests.test_word_completion import MemoryAnki


class TestSourceAPI(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name).resolve()
        self.words = root / "words_to_add.txt"
        self.words.write_bytes(b"same\nsame\n")
        self.service: Any = FactoryService.__new__(FactoryService)
        self.service.sessions = SessionStore(root / "test.sqlite3", root)
        self.service.anki = Mock()
        self.service.remote_preparation = Mock()
        self.session = self.service.session(self.service.list_sessions()[0]["id"])
        # Import actual routes without constructing real integrations or personal stores.
        with patch("backend.services.FactoryService", return_value=self.service):
            self.routes = importlib.import_module("backend.app")

    def request(self, method, path, body=None):
        async def invoke():
            messages = []

            async def receive():
                return {
                    "type": "http.request",
                    "body": json.dumps(body).encode() if body is not None else b"",
                }

            async def send(message):
                messages.append(message)

            scope = {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": [(b"content-type", b"application/json")],
                "client": ("127.0.0.1", 1234),
                "server": ("127.0.0.1", 8000),
            }
            with patch.object(self.routes, "service", self.service):
                await self.routes.app(scope, receive, send)
            status = next(
                message["status"]
                for message in messages
                if message["type"] == "http.response.start"
            )
            content = b"".join(
                message.get("body", b"")
                for message in messages
                if message["type"] == "http.response.body"
            )
            return status, json.loads(content)

        return asyncio.run(invoke())

    def test_discard_requires_entry_id_and_rejects_repeated_stale_browser_request(self):
        path = f"/backend/sessions/{self.session['id']}/current/discard"
        self.assertEqual(self.request("POST", path, {})[0], 422)
        body = {"entryId": self.session["current"]["id"]}
        status, result = self.request("POST", path, body)
        self.assertEqual(status, 200)
        self.assertEqual(result["remainingCount"], 1)
        self.assertEqual(self.request("POST", path, body)[0], 409)
        self.assertEqual(self.words.read_bytes(), b"same\n")
        self.assertEqual(self.service.anki.mock_calls, [])
        self.service.remote_preparation.notify.assert_called_once_with()

    def test_node_health_has_a_separate_route_without_anki_or_scheduler_actions(self):
        expected = {"configured": True, "healthy": True, "message": "Node API is online."}
        with patch.object(self.routes, "check_remote_node", return_value=expected) as probe:
            status, result = self.request("GET", "/backend/remote-node/health")
        self.assertEqual(status, 200)
        self.assertEqual(result, expected)
        probe.assert_called_once_with()
        self.assertEqual(self.service.anki.mock_calls, [])
        self.assertEqual(self.service.remote_preparation.mock_calls, [])

    def test_home_counts_are_live_and_retired_mutation_routes_are_unavailable(self):
        self.words.write_bytes(b"same\nsame\nnew\n")
        status, sources = self.request("GET", "/backend/sessions")
        self.assertEqual(status, 200)
        self.assertEqual(sources[0]["remainingCount"], 3)
        base = f"/backend/sessions/{self.session['id']}"
        for method, path, body in [
            ("POST", "/backend/sessions", {"words": ["import"]}),
            ("POST", "/backend/sessions/from-words-to-add", {}),
            ("PATCH", f"{base}/queue", {"words": []}),
            ("POST", f"{base}/queue/diff", {"words": []}),
            ("DELETE", base, None),
            ("DELETE", f"{base}/current/duplicate", None),
            (
                "POST",
                f"{base}/current/duplicate/suspend",
                {"entryId": self.session["current"]["id"]},
            ),
            ("POST", f"{base}/current/skip", {}),
        ]:
            with self.subTest(path=path):
                self.assertIn(self.request(method, path, body)[0], (404, 405))
        self.assertEqual(self.words.read_bytes(), b"same\nsame\nnew\n")
        self.assertEqual(self.service.anki.mock_calls, [])

    def test_acknowledged_creation_warning_and_local_only_removal_retry(self):
        self.service.completions = WordCompletion(self.service.sessions.path, self.words)
        self.service.anki = MemoryAnki()
        self.service.anki.bad_read = True
        self.service.notes = Mock()
        self.service.diki = Mock(last_error="No audio")
        self.service.diki.fetch_audio.side_effect = NoAudio("No audio")
        self.service.sessions.update_session(
            self.session["id"],
            deck_name="English",
            model_name="Basic",
            field_mapping={"englishField": "en_word", "translationField": "pl_translation"},
        )
        self.service.sessions.replace_current_draft(
            self.session["id"], {"word": "same", "groups": []}
        )
        base = f"/backend/sessions/{self.session['id']}"
        retry = f"{base}/current/retry-removal"
        body = {"entryId": self.session["current"]["id"]}
        self.assertEqual(self.request("POST", retry, {})[0], 422)
        self.assertEqual(self.request("POST", retry, body)[0], 409)
        with patch.object(
            self.service.sessions, "complete_current", side_effect=OSError("disk full")
        ):
            status, result = self.request(
                "POST", f"{base}/current/commit", {**body, "action": "create"}
            )
        self.assertEqual(status, 200)
        self.assertFalse(result["verified"])
        self.assertTrue(result["cleanupPending"])
        self.assertIn("notesInfo", result["confirmationWarning"])
        self.assertIn("disk full", result["cleanupWarning"])
        self.assertEqual(self.words.read_bytes(), b"same\nsame\n")
        self.service.remote_preparation.notify.assert_not_called()
        self.service.anki = Mock()
        status, reopened = self.request("GET", base)
        self.assertEqual(status, 200)
        self.assertEqual(reopened["pendingRemoval"]["noteId"], 123)
        status, retried = self.request("POST", retry, body)
        self.assertEqual(status, 200)
        self.assertFalse(retried["cleanupPending"])
        self.assertIn("notesInfo", retried["confirmationWarning"])
        self.assertEqual(self.words.read_bytes(), b"same\n")
        self.assertEqual(self.request("POST", retry, body)[0], 409)
        self.assertEqual(self.service.anki.mock_calls, [])
        self.service.remote_preparation.notify.assert_called_once_with()

    def test_application_lifespan_owns_one_scheduler_and_closes_it_before_integrations(self):
        preparation = Mock()
        self.service.diki = Mock()
        self.service.flush_sync = Mock()

        async def lifecycle():
            with (
                patch.object(self.routes, "service", self.service),
                patch.object(
                    self.routes.RemotePreparation, "from_environment", return_value=preparation
                ) as configure,
            ):
                async with self.routes.lifespan(self.routes.app):
                    self.assertIs(self.service.remote_preparation, preparation)
                    preparation.start.assert_called_once_with()
                    preparation.close.assert_not_called()
                configure.assert_called_once_with(self.service.diki.resources.root)
            preparation.close.assert_called_once_with()
            self.service.diki.resources.close.assert_called_once_with()
            self.assertIsNone(self.service.remote_preparation)

        asyncio.run(lifecycle())
