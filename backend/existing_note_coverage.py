"""Saved-first HTML statistics and one read-only Anki reconciliation per launch."""

import hashlib
import logging
import sqlite3
import threading
import time
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from external_apis.diki_inventory import export_inventory, load_inventory, save_inventory
from external_apis.diki_page import inspect_page
from external_apis.diki_resources import DikiResources, file_lock

log = logging.getLogger(__name__)
CATEGORIES = (
    ("entries", "Entries"),
    ("suggestions", "Spelling suggestions"),
    ("related", "Related entries"),
    ("collocation", "Collocations"),
    ("not_found", "Not found"),
    ("unknown", "Unknown HTML"),
    ("missing", "Missing HTML"),
    ("unusable", "Unusable HTML"),
    ("unprocessable", "Unprocessable English field"),
)


def html_coverage(inventory, resources, classifications, *, progress=None):
    """Inspect integrity-checked cached bytes only; exact-match/audio flags are irrelevant."""
    legacy = inventory.get("version") != 2
    notes = inventory.get("notes", []) if not legacy else []
    counts = dict.fromkeys((key for key, _ in CATEGORIES), 0)
    review = []
    kinds = {}
    used_digests = set()
    if progress is not None:
        progress("Classifying existing-note HTML", 0, len(notes))
    for completed, note in enumerate(notes, 1):
        word = note.get("word")
        reason = note.get("error")
        if reason:
            kind = "unprocessable"
        else:
            if word not in kinds:
                # Distinguish absent downloads from existing, unverifiable files.
                # Keep both checks consistent with concurrent cache imports.
                with file_lock(
                    resources.root / "cache.lock",
                    deadline=resources.deadline,
                    clock=resources.clock,
                    sleep=resources.sleep,
                ):
                    content = resources._read_cached(word, "html")
                    if content is None:
                        try:
                            resources.path(word, "html").stat()
                        except FileNotFoundError:
                            kinds[word] = "missing"
                        except OSError:
                            kinds[word] = "unusable"
                        else:
                            kinds[word] = "unusable"
                if content is not None:
                    digest = hashlib.sha256(content).hexdigest()
                    used_digests.add(digest)
                    if digest not in classifications:
                        classifications[digest] = inspect_page(
                            BeautifulSoup(content.decode("utf-8", errors="replace"), "html.parser")
                        ).kind
                    kinds[word] = classifications[digest]
            kind = kinds[word]
            if kind == "missing":
                reason = "No local HTML file is available; download is missing"
            elif kind == "unusable":
                reason = (
                    "Local HTML exists but cannot be read or verified against its cached digest"
                )
            elif kind != "entries":
                reason = "Cached page is not classified as full English→Polish entries"
        counts[kind] += 1
        if kind != "entries":
            review.append({**note, "category": kind, "reason": reason})
        if progress is not None:
            progress("Classifying existing-note HTML", completed, len(notes))
    # Retain only classifications used by the current snapshot, bounded by its size.
    for digest in list(classifications):
        if digest not in used_digests:
            del classifications[digest]
    total = len(notes)
    return {
        "available": bool(inventory.get("available", True)) and not legacy,
        "legacy": bool(inventory.get("available", True)) and legacy,
        "snapshotAt": inventory.get("createdAt"),
        "profile": inventory.get("profile"),
        "total": total,
        "entries": counts["entries"],
        "percent": round(100 * counts["entries"] / total, 1) if total else 0,
        "categories": [
            {
                "key": key,
                "label": label,
                "count": counts[key],
                "percent": round(100 * counts[key] / total, 1) if total else 0,
            }
            for key, label in CATEGORIES
        ],
        "review": review,
    }


def inventory_changes(previous, current):
    if previous.get("version") != 2:
        return None
    before = {note["noteId"]: note for note in previous["notes"]}
    after = {note["noteId"]: note for note in current["notes"]}
    return {
        "added": len(after.keys() - before.keys()),
        "removed": len(before.keys() - after.keys()),
        "changed": sum(before[key] != after[key] for key in before.keys() & after.keys()),
    }


class ExistingNoteCoverage:
    def __init__(self, root, api_factory, notes, *, on_reconciled=None, refresh_interval=60):
        self.root = root
        self.api_factory = api_factory
        self.notes = notes
        self.on_reconciled = on_reconciled
        self.refresh_interval = refresh_interval
        self._next_refresh = 0
        self._busy = True
        self.stop = threading.Event()
        self.changed = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self._state = {
            "available": False,
            "loading": True,
            "progress": {"stage": "Reading saved note inventory", "processed": 0, "total": None},
            "reconciliation": "starting",
            "reconciliationError": None,
            "cacheError": None,
            "reconciledAt": None,
            "indexIssues": [],
            "indexError": None,
            "changes": None,
        }

    def _update(self, **values):
        with self.lock:
            self._state = {**self._state, **values}

    def status(self):
        with self.lock:
            # Reserve one scan when due; progress polling never queues follow-up scans.
            if not self.stop.is_set() and not self._busy and time.monotonic() >= self._next_refresh:
                self._busy = True
                self._state = {
                    **self._state,
                    "loading": True,
                    "progress": {
                        "stage": "Reading saved note inventory",
                        "processed": 0,
                        "total": None,
                    },
                }
                self.changed.set()
            return dict(self._state)

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def close(self):
        self.stop.set()
        self.changed.set()

    def _refresh(self, resources, classifications):
        self._update(
            loading=True,
            progress={
                "stage": "Reading saved note inventory",
                "processed": 0,
                "total": None,
            },
        )
        try:
            inventory = load_inventory()
            report = html_coverage(inventory, resources, classifications, progress=self._progress)
            if not self.stop.is_set():
                self._update(**report, cacheError=None)
            return inventory
        finally:
            self._update(loading=False)

    def _progress(self, stage, processed, total):
        if self.stop.is_set():
            raise InterruptedError("Note classification stopped")
        self._update(progress={"stage": stage, "processed": processed, "total": total})

    def _idle(self):
        with self.lock:
            self._busy = False
            self._next_refresh = time.monotonic() + self.refresh_interval

    def _run(self):
        try:
            with DikiResources(self.root, offline=True) as resources:
                self._work(resources)
        except Exception:
            log.exception("Existing-note coverage worker stopped unexpectedly")
            self._update(
                cacheError="Coverage worker stopped; check local logs",
                reconciliation="error",
                loading=False,
            )
            self.stop.set()

    def _work(self, resources):
        classifications = {}
        previous = {}
        try:
            previous = self._refresh(resources, classifications)
        except (OSError, ValueError, sqlite3.Error) as error:
            self._update(cacheError=str(error))
        if self.stop.is_set():
            return
        self._update(reconciliation="checking")
        try:
            # Own the Anki client: last_error is mutable and interactive lookups use theirs.
            current = export_inventory(self.api_factory(), cancelled=self.stop.is_set)
            if self.stop.is_set():
                return
            if previous.get("profile") and previous["profile"] != current["profile"]:
                raise ValueError(
                    "Active Anki profile differs from the saved inventory; "
                    "switch back or explicitly export the intended profile"
                )
            save_inventory(current)
            try:
                issues = self.notes.inventory_discrepancies(current)
                self._update(indexIssues=issues, indexError=None)
            except sqlite3.Error as error:
                self._update(indexError=str(error))
            self._refresh(resources, classifications)
            self._update(
                reconciliation="complete",
                reconciledAt=datetime.now(UTC).isoformat(),
                changes=inventory_changes(previous, current),
            )
            if self.on_reconciled is not None and not self.stop.is_set():
                self.on_reconciled()
        except (OSError, ValueError, sqlite3.Error) as error:
            if self.stop.is_set():
                return
            self._update(reconciliation="error", reconciliationError=str(error))
        self._idle()
        while not self.stop.is_set():
            self.changed.wait()
            self.changed.clear()
            if self.stop.is_set():
                break
            try:
                self._refresh(resources, classifications)
            except (OSError, ValueError, sqlite3.Error) as error:
                self._update(cacheError=str(error))
            finally:
                self._idle()
