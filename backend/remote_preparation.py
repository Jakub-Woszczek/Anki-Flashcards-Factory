"""Application-scoped, event-driven remote preparation with one startup drain."""

import logging
import os
import threading
from pathlib import Path

from external_apis.diki_inventory import load_inventory
from external_apis.diki_lists import discover_lists
from external_apis.diki_remote import RemoteDownloads, RemoteError, RemoteStopped
from external_apis.diki_resources import DikiResources, file_lock

log = logging.getLogger(__name__)
BUFFER_ENTRIES = 100


class RemotePreparation:
    def __init__(self, root: Path, client_factory, *, words_dir=None, inventory_loader=None):
        self.root = root
        self.client_factory = client_factory
        self.words_dir = words_dir
        self.inventory_loader = inventory_loader or load_inventory
        self.stop = threading.Event()
        self.changed = threading.Event()
        self.lock = threading.Lock()
        self.threads: list[threading.Thread] = []
        self._ownership = None
        self._active = 0
        self._state = {
            "enabled": True,
            "bufferEntries": BUFFER_ENTRIES,
            "submission": "starting",
            "drain": "starting",
            "queued": 0,
            "wordsImported": 0,
            "coverageAvailable": False,
            "coverageWords": 0,
            "coverageInvalid": 0,
            "submissionError": None,
            "drainError": None,
        }

    @classmethod
    def from_environment(cls, root):
        url, token = os.getenv("DIKI_REMOTE_URL", ""), os.getenv("DIKI_REMOTE_TOKEN", "")
        if not url and not token:
            return None
        return cls(root, lambda **kwargs: RemoteDownloads(url, token, **kwargs))

    def status(self):
        with self.lock:
            return dict(self._state)

    def _update(self, **values):
        with self.lock:
            self._state.update(values)

    def notify(self):
        if not self.stop.is_set():
            self.changed.set()

    def start(self):
        self._ownership = file_lock(self.root / "remote-scheduler.lock", blocking=False)
        try:
            self._ownership.__enter__()
        except OSError as error:
            self._ownership = None
            self._update(
                submission="error",
                drain="error",
                submissionError="Another app owns remote preparation for this cache"
                if isinstance(error, BlockingIOError)
                else f"Cannot start remote preparation: {error}",
            )
            return
        self._active = 2
        self.notify()
        for target in (self._submit_loop, self._startup_drain):
            worker = threading.Thread(target=self._run, args=(target,), daemon=True)
            self.threads.append(worker)
            worker.start()

    def _run(self, target):
        try:
            target()
        except Exception:
            # Keep unexpected background failures out of save/source request paths.
            log.exception("Remote preparation worker stopped unexpectedly")
            message = "Unexpected remote preparation failure; check local logs"
            if target == self._startup_drain:
                self._update(drain="error", drainError=message)
            else:
                self._update(submission="error", submissionError=message)
        finally:
            with self.lock:
                self._active -= 1
                if self._active == 0 and self._ownership is not None:
                    self._ownership.__exit__(None, None, None)
                    self._ownership = None

    def _submit_loop(self):
        client = None
        try:
            client = self.client_factory(stop=self.stop, preserve_existing=True)
            with DikiResources(self.root, offline=True) as resources:
                compatible = False
                while not self.stop.is_set():
                    self.changed.wait()
                    self.changed.clear()
                    if self.stop.is_set():
                        break
                    try:
                        if not compatible:
                            client.require_scheduling()
                            compatible = True
                        self.reconcile(client, resources)
                    except RemoteStopped:
                        break
                    except (RemoteError, OSError, ValueError) as error:
                        self._update(submission="error", submissionError=str(error))
        except (RemoteError, ValueError) as error:
            self._update(submission="error", submissionError=str(error))
        finally:
            if client is not None:
                client.close()

    def reconcile(self, client, resources):
        self._update(submission="submitting", submissionError=None)
        lists = discover_lists(self.words_dir, entry_limit=BUFFER_ENTRIES)
        errors = [f"{source.name}: {source.error}" for source in lists if source.error]
        invalid = sum(source.invalid for source in lists)
        words = list(dict.fromkeys(word for source in lists for word in source.words))
        result = client.submit(words, resources, priority="buffer", remember=True)
        queued = result["queued"]
        self._update(queued=self.status()["queued"] + queued)
        inventory = self.inventory_loader()
        self._update(
            coverageAvailable=inventory.get("available", True),
            coverageWords=len(inventory["words"]),
            coverageInvalid=inventory.get("invalidCount", 0),
        )
        window = set(words)
        coverage = [word for word in inventory["words"] if word not in window]
        if coverage:
            result = client.submit(
                coverage, resources, html_only=True, priority="coverage", remember=True
            )
            self._update(queued=self.status()["queued"] + result["queued"])
        if invalid:
            errors.append(f"{invalid} invalid buffer entries need review")
        self._update(
            submission="idle",
            submissionError="; ".join(errors) if errors else None,
        )

    def _startup_drain(self):
        client = None
        try:
            client = self.client_factory(stop=self.stop, preserve_existing=True)
            with DikiResources(self.root, offline=True) as resources:
                self._update(drain="downloading", drainError=None)
                result = client.pull(resources, startup=True)
                self._update(drain="complete", wordsImported=result["wordsImported"])
                # Newly imported coverage HTML may make an audio-only buffer goal possible.
                self.notify()
        except RemoteStopped:
            self._update(drain="interrupted")
        except (RemoteError, OSError, ValueError) as error:
            self._update(drain="error", drainError=str(error))
        finally:
            if client is not None:
                client.close()

    def close(self):
        # Workers own their clients/resources and journals. No network join here.
        self.stop.set()
        self.changed.set()
