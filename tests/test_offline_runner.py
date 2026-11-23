"""Verify the enforced test boundary without making any network requests."""

import io
import os
import socket
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.test_offline import main


class TestOfflineRunner(unittest.TestCase):
    def test_blocks_network_and_temporarily_disables_live_checks(self):
        transports = [Mock(), Mock(), Mock()]

        def probe():
            self.assertEqual(os.environ["RUN_LIVE_DIKI_TESTS"], "0")
            self.assertEqual(os.environ["RUN_LOOPBACK_TESTS"], "0")
            self.assertEqual(os.environ["DIKI_REMOTE_URL"], "")
            self.assertEqual(os.environ["DIKI_REMOTE_TOKEN"], "")
            self.assertEqual(os.environ["DIKI_OFFLINE"], "0")
            sandbox = Path(os.environ["ANKI_FACTORY_DATA_DIR"])
            self.assertTrue(sandbox.is_dir())
            self.assertIn("anki-factory-tests-", sandbox.name)
            with socket.socket() as client:
                with self.assertRaisesRegex(AssertionError, "Live network"):
                    client.connect(("127.0.0.1", 8765))
                with self.assertRaisesRegex(AssertionError, "Live network"):
                    client.connect_ex(("127.0.0.1", 8765))
            with self.assertRaisesRegex(AssertionError, "Live DNS"):
                socket.getaddrinfo("www.diki.pl", 443)

        runner = unittest.TextTestRunner(stream=io.StringIO())
        suite = unittest.TestSuite([unittest.FunctionTestCase(probe)])
        with (
            patch.dict(
                os.environ,
                {"RUN_LIVE_DIKI_TESTS": "1", "RUN_LOOPBACK_TESTS": "1", "DIKI_OFFLINE": "1"},
            ),
            patch.object(socket.socket, "connect", transports[0]),
            patch.object(socket.socket, "connect_ex", transports[1]),
            patch("socket.getaddrinfo", transports[2]),
            patch("tools.test_offline.unittest.defaultTestLoader.discover", return_value=suite),
            patch("tools.test_offline.unittest.TextTestRunner", return_value=runner),
        ):
            self.assertEqual(main(), 0)
            self.assertEqual(os.environ["RUN_LIVE_DIKI_TESTS"], "1")
            self.assertEqual(os.environ["RUN_LOOPBACK_TESTS"], "1")
            self.assertEqual(os.environ["DIKI_OFFLINE"], "1")
        for transport in transports:
            transport.assert_not_called()

    def test_accidental_network_request_fails_the_run(self):
        def accidental_request():
            socket.getaddrinfo("www.diki.pl", 443)

        output = io.StringIO()
        runner = unittest.TextTestRunner(stream=output)
        suite = unittest.TestSuite([unittest.FunctionTestCase(accidental_request)])
        with (
            patch("tools.test_offline.unittest.defaultTestLoader.discover", return_value=suite),
            patch("tools.test_offline.unittest.TextTestRunner", return_value=runner),
        ):
            self.assertEqual(main(), 1)
        self.assertIn("Live DNS lookup in offline tests", output.getvalue())
