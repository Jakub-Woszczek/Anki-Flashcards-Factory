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
