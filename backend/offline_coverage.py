"""Application-scoped local coverage scans; HTTP requests only read their progress."""

import logging
import sqlite3
import threading
import time

from external_apis.diki_lists import coverage
from external_apis.diki_resources import DikiResources

log = logging.getLogger(__name__)


class OfflineCoverage:
    def __init__(self, root, *, refresh_interval=60):
        self.root = root
        self.refresh_interval = refresh_interval
        self.stop = threading.Event()
        self.changed = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self._next_refresh = 0
        self._state = {
            "lists": [],
            "lastRun": None,
            "cooldownUntil": 0,
            "cooldownReason": None,
            "listsAvailable": False,
            "loading": True,
            "progress": {"stage": "Reading cache index", "processed": 0, "total": None},
            "coverageError": None,
        }

    def start(self):
        if self.thread is None:
            self.changed.set()
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def status(self):
        with self.lock:
            if (
                not self.stop.is_set()
                and not self._state["loading"]
                and time.monotonic() >= self._next_refresh
            ):
                self._state = {
                    **self._state,
                    "loading": True,
                    "coverageError": None,
                    "progress": {"stage": "Reading cache index", "processed": 0, "total": None},
                }
                self.changed.set()
            return dict(self._state)

    def close(self):
        self.stop.set()
        self.changed.set()

    def _progress(self, stage, processed, total):
        if self.stop.is_set():
            raise InterruptedError("Coverage scan stopped")
        with self.lock:
            self._state = {
                **self._state,
                "progress": {
                    "stage": stage,
                    "processed": processed,
                    "total": total,
                },
            }

    def _finish(self, **values):
        with self.lock:
            self._next_refresh = time.monotonic() + self.refresh_interval
            self._state = {**self._state, **values, "loading": False}

    def _run(self):
        try:
            with DikiResources(self.root, offline=True) as resources:
                while not self.stop.is_set():
                    self.changed.wait()
                    self.changed.clear()
                    if self.stop.is_set():
                        break
                    try:
                        result = coverage(resources, progress=self._progress)
                        if not self.stop.is_set():
                            self._finish(**result, listsAvailable=True, coverageError=None)
                    except (OSError, ValueError, sqlite3.Error) as error:
                        if not self.stop.is_set():
                            self._finish(coverageError=str(error))
        except Exception:
            log.exception("Offline coverage worker stopped unexpectedly")
            self.stop.set()
            self._finish(
                coverageError="Coverage worker stopped; restart the app and check local logs"
            )
