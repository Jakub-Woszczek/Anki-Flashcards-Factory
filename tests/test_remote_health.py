"""Connection checks must be authenticated, bounded, read-only, and offline-testable."""

import json
import os
from unittest import TestCase
from unittest.mock import Mock, patch

import requests

from backend.remote_health import check_remote_node
from external_apis.diki_remote import RemoteDownloads
from tests.test_diki_resources import response

URL = "https://node-health.example"
TOKEN = "test-only-node-health-token-" * 3


class TestRemoteHealth(TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"DIKI_REMOTE_URL": URL, "DIKI_REMOTE_TOKEN": TOKEN})
        environment.start()
        self.addCleanup(environment.stop)

    def probe(self, payload, *, status=200, error=None):
        session = Mock()
        session.headers = {}
        session.request.return_value = response(json.dumps(payload).encode(), status)
        session.request.side_effect = error
        with patch(
            "backend.remote_health.RemoteDownloads",
            side_effect=lambda url, token: RemoteDownloads(url, token, session=session),
        ):
            result = check_remote_node()
        session.close.assert_called_once_with()
        return result, session

    def test_online_check_uses_authenticated_read_only_status_with_short_timeouts(self):
        result, session = self.probe({"protocol": 2, "jobs": {}, "schedulingVersion": 1})
        self.assertTrue(result["healthy"])
        self.assertTrue(result["schedulingAvailable"])
        session.request.assert_called_once_with(
            "GET", URL + "/v1/status", timeout=(2, 3), allow_redirects=False, stream=True
        )
        self.assertEqual(session.headers["Authorization"], "Bearer " + TOKEN)
        self.assertFalse(session.trust_env)
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_unconfigured_or_partial_configuration_does_not_attempt_http(self):
        for url, token in [("", ""), (URL, ""), ("", TOKEN)]:
            with self.subTest(url=url, has_token=bool(token)):
                with (
                    patch.dict(os.environ, {"DIKI_REMOTE_URL": url, "DIKI_REMOTE_TOKEN": token}),
                    patch("backend.remote_health.RemoteDownloads") as client,
                ):
                    result = check_remote_node()
                self.assertFalse(result["configured"])
                self.assertFalse(result["healthy"])
                client.assert_not_called()

    def test_authentication_failure_does_not_expose_response_content_or_token(self):
        result, _ = self.probe({"secret": TOKEN}, status=401)
        self.assertTrue(result["configured"])
        self.assertFalse(result["healthy"])
        self.assertIn("HTTP 401", result["message"])
        self.assertNotIn(TOKEN, json.dumps(result))

    def test_timeout_is_an_offline_result_instead_of_a_backend_error(self):
        result, _ = self.probe({}, error=requests.ReadTimeout("fake timeout"))
        self.assertFalse(result["healthy"])
        self.assertIn("ReadTimeout", result["message"])

    def test_unexpected_service_response_is_not_reported_online(self):
        for payload in [
            None,
            {"protocol": True, "jobs": {}},
            {"protocol": 99, "jobs": {}},
            {"protocol": 2, "jobs": "invalid"},
        ]:
            with self.subTest(payload=payload):
                result, _ = self.probe(payload)
                self.assertFalse(result["healthy"])

    def test_online_node_is_distinct_from_scheduling_support_or_diki_cooldown(self):
        result, _ = self.probe({"protocol": 2, "jobs": {}, "cooldownUntil": 9999999999})
        self.assertTrue(result["healthy"])
        self.assertFalse(result["schedulingAvailable"])
        self.assertIn("update the worker", result["message"])
