"""Run unit tests with real network access blocked; live checks stay explicit."""

import os
import socket
import unittest
from unittest.mock import patch

from backend.settings import ROOT_DIR


def main() -> int:
    # Do not load .env or set DIKI_OFFLINE: fake HTTP must still exercise fetching.
    with (
        patch.dict(os.environ, {"RUN_LIVE_DIKI_TESTS": "0", "DIKI_OFFLINE": "0"}),
        patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("Live network access in offline tests"),
        ),
        patch.object(
            socket.socket,
            "connect_ex",
            side_effect=AssertionError("Live network access in offline tests"),
        ),
        patch("socket.getaddrinfo", side_effect=AssertionError("Live DNS lookup in offline tests")),
    ):
        suite = unittest.defaultTestLoader.discover(
            start_dir=str(ROOT_DIR / "tests"), top_level_dir=str(ROOT_DIR)
        )
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
