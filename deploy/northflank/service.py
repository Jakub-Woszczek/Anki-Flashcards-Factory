"""Durable single-consumer download queue and acknowledge-before-delete outbox."""

import base64
import json
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import requests
from urllib3.exceptions import HTTPError as UrllibError

from external_apis.diki_audio import DISCOVERY_VERSION, validate_audio_plan
from external_apis.diki_resources import (
    TIMEOUT,
    BatchDeadline,
    Deferred,
    DikiResources,
    DikiServerError,
    DikiTimeout,
    NoAudio,
    ResourceError,
    file_lock,
    normalize_word,
)
from external_apis.diki_transfer import (
    LIMITS,
    MAX_ITEMS,
    MAX_MANIFEST_BYTES,
    MAX_TRANSFER_BYTES,
    PROTOCOL,
    canonical,
    digest,
    html_source,
    validate_artifact,
    validate_html,
    validate_manifest,
)

log = logging.getLogger(__name__)


class QueueConflict(Exception):
    pass


def stored_envelope(value):
    try:
        envelope = json.loads(value)
        validate_manifest(envelope)
        return envelope
    except ValueError:
        raise QueueConflict(
            "Stored manifest corrupt; restore from backup; no automatic redownload was attempted"
        ) from None


class PauseWork(Deferred):
    def __init__(self, reason, until: float = 0):
        super().__init__(reason)
        self.until = until


class BoundedResponse:
    def __init__(self, response, stop, deadline):
        self.response, self.stop, self.deadline = response, stop, deadline
        self.status_code, self.headers = response.status_code, response.headers

    def close(self):
        self.response.close()

    def iter_content(self, size):
        # read1 returns available bytes instead of waiting to fill a 64 KiB chunk.
        # Check elapsed time even if a server continuously trickles its response.
        while True:
            if self.stop.is_set():
                raise PauseWork("Worker stopping")
            if time.monotonic() >= self.deadline:
                raise DikiTimeout("Diki response exceeded the remote transfer deadline")
            try:
                chunk = self.response.raw.read1(size, decode_content=True)
            except UrllibError:
                raise requests.ReadTimeout("Diki response stream failed") from None
            if not chunk:
                return
            yield chunk


class DownloadService:
    def __init__(self, config, *, clock=time.time, monotonic=time.monotonic, sleep=None, get=None):
        self.config = config.validate()
        self.clock = clock
        self.monotonic = monotonic
        self.stop_event, self.wake = threading.Event(), threading.Event()
        self.lock, self.cycle_lock = threading.RLock(), threading.Lock()
        self.thread, self.worker_lock = None, None
        self.resources = DikiResources(
            config.data_dir,
            profile="background",
            offline=False,
            clock=clock,
            sleep=sleep or self._sleep,
            get=get or self._get,
            before_request=self._reserve_request,
            retain_headwords=False,
        )
        self.resources.session.trust_env = False
        with self.resources.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS remote_jobs (
                    id TEXT PRIMARY KEY, word TEXT UNIQUE NOT NULL,
                    state TEXT NOT NULL, need_audio INTEGER NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    retry_at REAL NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
                    error TEXT, audio_state TEXT, artifacts TEXT, batch_id TEXT,
                    cleaned INTEGER NOT NULL DEFAULT 0, audio_plan TEXT
                );
                CREATE INDEX IF NOT EXISTS remote_pending ON remote_jobs(state,retry_at,created_at);
                CREATE TABLE IF NOT EXISTS remote_usage (
                    day TEXT PRIMARY KEY, requests INTEGER NOT NULL DEFAULT 0,
                    work_seconds REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS remote_batches (
                    id TEXT PRIMARY KEY, envelope TEXT NOT NULL,
                    created_at REAL NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS remote_drains (
                    id TEXT PRIMARY KEY, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS remote_drain_jobs (
                    drain_id TEXT NOT NULL, job_id TEXT NOT NULL,
                    PRIMARY KEY(drain_id,job_id)
                );
            """)
            # Existing queues and stable protocol-1 outboxes remain recoverable.
            db.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in db.execute("PRAGMA table_info(remote_jobs)")}
            if "audio_plan" not in columns:
                db.execute("ALTER TABLE remote_jobs ADD COLUMN audio_plan TEXT")
            if "priority" not in columns:
                db.execute("ALTER TABLE remote_jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
            if "followup" not in columns:
                db.execute("ALTER TABLE remote_jobs ADD COLUMN followup TEXT")

    def _sleep(self, seconds):
        if self.stop_event.wait(seconds):
            raise PauseWork("Worker stopping")

    def _get(self, url, **kwargs):
        # Leave one socket-read timeout inside DikiResources' TIMEOUT allowance.
        # A trickling body cannot extend the work slice indefinitely.
        end = time.monotonic() + TIMEOUT - 5
        response = self.resources.session.get(
            url, headers=kwargs["headers"], timeout=(5, 5), stream=True, allow_redirects=False
        )
        return BoundedResponse(response, self.stop_event, end)

    def _day(self):
        now = datetime.fromtimestamp(self.clock(), UTC)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return now.date().isoformat(), tomorrow.timestamp()

    def _storage(self, additional=0):
        with self.resources.db() as db:
            used = db.execute(
                "SELECT COALESCE(SUM(size),0) FROM resources WHERE digest IS NOT NULL"
            ).fetchone()[0]
        if used + additional > self.config.pending_bytes:
            raise PauseWork(
                "Pending download storage budget reached; pull completed transfers",
                self.clock() + 300,
            )
        if shutil.disk_usage(self.config.data_dir).free < self.config.min_free_bytes + additional:
            raise PauseWork("Persistent volume is low on free space", self.clock() + 300)
        return used

    def _reserve_request(self, url, kind):
        if self.stop_event.is_set():
            raise PauseWork("Worker stopping")
        self._storage(LIMITS[kind])
        day, tomorrow = self._day()
        with self.resources.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO remote_usage(day) VALUES (?)", (day,))
            used = db.execute("SELECT requests FROM remote_usage WHERE day=?", (day,)).fetchone()[0]
            if used >= self.config.requests_per_day:
                raise PauseWork("Daily HTTP request budget exhausted", tomorrow)
            # Reserve before the HTTP attempt. A killed process cannot refund it.
            db.execute("UPDATE remote_usage SET requests=requests+1 WHERE day=?", (day,))

    def _reserve_runtime(self):
        day, tomorrow = self._day()
        with self.resources.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO remote_usage(day) VALUES (?)", (day,))
            used = db.execute(
                "SELECT work_seconds FROM remote_usage WHERE day=?", (day,)
            ).fetchone()[0]
            seconds = min(
                self.config.batch_seconds,
                self.config.work_seconds_per_day - used,
                tomorrow - self.clock(),
            )
            if seconds <= TIMEOUT:
                raise PauseWork("Daily worker-runtime budget exhausted", tomorrow)
            db.execute(
                "UPDATE remote_usage SET work_seconds=work_seconds+? WHERE day=?", (seconds, day)
            )
        return day, seconds

    def _state(self, state, message=None):
        self.resources.set_setting(
            "remote_state", {"state": state, "message": message, "at": self.clock()}
        )

    def submit(self, records, *, redownload=False, retry_failed=False):
        prepared = {}
        for record in records:
            word = normalize_word(record["word"])
            content = None
            audio_plan = record.get("audio_plan")
            priority = record.get("priority", "buffer")
            if priority not in {"buffer", "coverage"}:
                raise ValueError("Unknown preparation priority")
            if priority == "coverage" and record.get("need_audio", True):
                raise ValueError("Existing-note coverage requests HTML only")
            if audio_plan is not None:
                validate_audio_plan(audio_plan)
                if record.get("html") is not None or not record.get("need_audio", True):
                    raise ValueError("Audio-only jobs cannot include HTML or disable audio")
            if record.get("html"):
                content = base64.b64decode(record["html"], validate=True)
                if len(content) > 512 * 1024:
                    raise ValueError("HTML seed exceeds 512 KiB")
                validate_html(content)
            goal = (
                bool(record.get("need_audio", True)),
                content,
                record.get("html_status", 200),
                audio_plan,
                0 if priority == "buffer" else 1,
            )
            previous = prepared.get(word)
            if previous is None:
                prepared[word] = goal
            else:
                strongest = goal if goal[0] and not previous[0] else previous
                prepared[word] = (*strongest[:4], min(previous[4], goal[4]))
        added, skipped = 0, 0
        with self.lock:
            self._cleanup_delivered()
            for word, (need_audio, seed, status, audio_plan, priority) in prepared.items():
                with self.resources.db() as db:
                    old = db.execute("SELECT * FROM remote_jobs WHERE word=?", (word,)).fetchone()
                    count = db.execute("SELECT COUNT(*) FROM remote_jobs").fetchone()[0]
                reset = old and (
                    (old["state"] == "delivered" and redownload and old["cleaned"])
                    or (old["state"] == "failed" and retry_failed)
                )
                if old and not reset:
                    if self._promote(old, need_audio, audio_plan, priority):
                        added += 1
                        continue
                    skipped += 1
                    continue
                if not old and count >= self.config.max_jobs:
                    raise QueueConflict("Queue/tombstone limit reached")
                if seed and self.resources._cached(word, "html") is None:
                    self._storage(len(seed))
                    from external_apis.diki_api import resolve_lookup

                    self.resources._save(
                        word,
                        "html",
                        seed,
                        status,
                        html_source(word),
                        bool(resolve_lookup(seed.decode(), word).meanings),
                    )
                with self.resources.db() as db:
                    if reset:
                        db.execute("DELETE FROM remote_jobs WHERE word=?", (word,))
                        db.execute("DELETE FROM resource_failures WHERE word=?", (word,))
                    db.execute(
                        """INSERT INTO remote_jobs(id,word,state,need_audio,created_at,updated_at,audio_plan,priority)
                        VALUES (?,?,'queued',?,?,?,?,?)""",
                        (
                            uuid.uuid4().hex,
                            word,
                            int(need_audio),
                            self.clock(),
                            self.clock(),
                            canonical(audio_plan).decode() if audio_plan is not None else None,
                            priority,
                        ),
                    )
                added += 1
        if added:
            self.wake.set()
        return {"queued": added, "alreadyKnown": skipped}

    def _promote(self, old, need_audio, audio_plan, priority):
        """Upgrade resource goals without rewriting an issued manifest or retrying failures."""
        with self.resources.db() as db:
            db.execute(
                "UPDATE remote_jobs SET priority=MIN(priority,?) WHERE id=?", (priority, old["id"])
            )
        if not need_audio or old["state"] == "failed":
            return False
        additional_audio = not old["need_audio"]
        if old["state"] in {"ready", "delivered"} and audio_plan and old["need_audio"]:
            artifacts = json.loads(old["artifacts"] or "[]")
            audio_sources = {item["source"] for item in artifacts if item["kind"] == "audio"}
            html_digests = {item["digest"] for item in artifacts if item["kind"] == "html"}
            previous_plan = json.loads(old["audio_plan"]) if old["audio_plan"] else None
            additional_audio = (
                old["audio_state"] in {"not_required", "not_requested"}
                or (bool(audio_sources) and not audio_sources.intersection(audio_plan["urls"]))
                or (
                    old["audio_state"] == "no_audio"
                    and (
                        (previous_plan is not None and previous_plan != audio_plan)
                        or (bool(html_digests) and audio_plan["htmlDigest"] not in html_digests)
                    )
                )
            )
        if (
            not additional_audio
            and audio_plan is not None
            and old["state"] in {"queued", "running"}
        ):
            previous_plan = json.loads(old["audio_plan"]) if old["audio_plan"] else None
            if previous_plan != audio_plan:
                if old["state"] == "queued":
                    with self.resources.db() as db:
                        db.execute(
                            "UPDATE remote_jobs SET audio_plan=? WHERE id=?",
                            (canonical(audio_plan).decode(), old["id"]),
                        )
                else:
                    with self.resources.db() as db:
                        db.execute(
                            "UPDATE remote_jobs SET followup=? WHERE id=?",
                            (
                                canonical(
                                    {"audio_plan": audio_plan, "priority": priority}
                                ).decode(),
                                old["id"],
                            ),
                        )
                return True
        if not additional_audio:
            return False
        plan_json = canonical(audio_plan).decode() if audio_plan is not None else None
        if old["state"] in {"queued", "running"}:
            with self.resources.db() as db:
                db.execute("UPDATE remote_jobs SET need_audio=1 WHERE id=?", (old["id"],))
                if old["state"] == "queued" and audio_plan is not None:
                    db.execute(
                        "UPDATE remote_jobs SET audio_plan=? WHERE id=?", (plan_json, old["id"])
                    )
            return True
        if (old["state"] == "ready" and old["batch_id"] is not None) or (
            old["state"] == "delivered" and not old["cleaned"]
        ):
            with self.resources.db() as db:
                db.execute(
                    "UPDATE remote_jobs SET followup=? WHERE id=?",
                    (
                        canonical({"audio_plan": audio_plan, "priority": priority}).decode(),
                        old["id"],
                    ),
                )
            return True
        if old["state"] == "ready" or (
            old["state"] == "delivered" and old["cleaned"] and audio_plan is not None
        ):
            # A fresh ID keeps snapshots and duplicate old ACKs generation-scoped.
            with self.resources.db() as db:
                db.execute(
                    """UPDATE remote_jobs SET id=?,state='queued',need_audio=1,
                    created_at=?,updated_at=?,retry_at=0,attempts=0,error=NULL,
                    audio_state=NULL,artifacts=NULL,batch_id=NULL,cleaned=0,audio_plan=?,followup=NULL
                    WHERE id=?""",
                    (uuid.uuid4().hex, self.clock(), self.clock(), plan_json, old["id"]),
                )
            return True
        return False

    def _set_job(self, identifier, state, *, retry_at: float = 0, error=None, failure=False):
        with self.lock, self.resources.db() as db:
            row = db.execute(
                "SELECT attempts FROM remote_jobs WHERE id=?", (identifier,)
            ).fetchone()
            attempts = row[0] + int(failure)
            if failure and attempts >= self.config.max_attempts:
                state = "failed"
            db.execute(
                "UPDATE remote_jobs SET state=?,retry_at=?,error=?,attempts=?,updated_at=? WHERE id=?",
                (state, retry_at, error, attempts, self.clock(), identifier),
            )

    def _ready(self, job, audio_state):
        resources = []
        kinds = (
            (["audio"] if audio_state == "ready" else [])
            if job["audio_plan"]
            else (["html", "audio"] if audio_state == "ready" else ["html"])
        )
        for kind in kinds:
            row = self.resources.metadata(job["word"], kind) or {}
            data = self.resources._cached(job["word"], kind)
            if data is None:
                raise OSError("Downloaded resource is missing/corrupt before export")
            artifact = {key: row[key] for key in ("kind", "digest", "size", "status", "source")}
            validate_artifact(artifact, data, job["word"])
            resources.append(artifact)
        with self.lock, self.resources.db() as db:
            current = db.execute(
                "SELECT need_audio FROM remote_jobs WHERE id=?", (job["id"],)
            ).fetchone()
            if current and current[0] and audio_state == "not_requested":
                db.execute("UPDATE remote_jobs SET state='queued' WHERE id=?", (job["id"],))
                return
            db.execute(
                "UPDATE remote_jobs SET state='ready',audio_state=?,artifacts=?,error=NULL,retry_at=0,updated_at=? WHERE id=?",
                (audio_state, json.dumps(resources), self.clock(), job["id"]),
            )

    def run_cycle(self):
        if not self.cycle_lock.acquire(blocking=False):
            return
        reservation, started, job = None, self.monotonic(), None
        try:
            with self.lock:
                self._cleanup_delivered()
            self.resources._check_pause()
            with self.resources.db() as db:
                pending = db.execute(
                    "SELECT 1 FROM remote_jobs WHERE state='queued' AND retry_at<=? LIMIT 1",
                    (self.clock(),),
                ).fetchone()
            if not pending:
                self._state("idle")
                return
            reservation = self._reserve_runtime()
            self.resources.deadline = self.clock() + reservation[1]
            for _ in range(self.config.batch_words):
                if self.stop_event.is_set():
                    break
                self.resources._check_pause()
                self.resources._check_budget()
                with self.lock, self.resources.db() as db:
                    job = db.execute(
                        """SELECT * FROM remote_jobs WHERE state='queued' AND retry_at<=?
                        ORDER BY priority,created_at,rowid LIMIT 1""",
                        (self.clock(),),
                    ).fetchone()
                    if job is None:
                        break
                    db.execute(
                        "UPDATE remote_jobs SET state='running',updated_at=? WHERE id=?",
                        (self.clock(), job["id"]),
                    )
                self._state("downloading")
                try:
                    if job["audio_plan"]:
                        try:
                            self.resources.fetch_audio_from_plan(
                                job["word"], json.loads(job["audio_plan"])
                            )
                            audio_state = "ready"
                        except NoAudio:
                            audio_state = "no_audio"
                    else:
                        self.resources.fetch_html(job["word"])
                        if not (self.resources.metadata(job["word"], "html") or {})["exact_match"]:
                            audio_state = "not_required"
                        elif not self._needs_audio(job["id"]):
                            audio_state = "not_requested"
                        else:
                            try:
                                self.resources.fetch_audio(job["word"])
                                audio_state = "ready"
                            except NoAudio:
                                audio_state = "no_audio"
                    self._ready(job, audio_state)
                    self.resources.set_setting("remote_server_errors", 0)
                except BatchDeadline:
                    self._set_job(job["id"], "queued")
                    break
                except PauseWork as error:
                    self._set_job(job["id"], "queued", retry_at=error.until)
                    raise
                except ResourceError as error:
                    # A new Blocked is a real response, while other Deferreds aren't.
                    from external_apis.diki_resources import Blocked

                    failure = not isinstance(error, Deferred) or isinstance(error, Blocked)
                    rows = [
                        self.resources.metadata(job["word"], kind) or {}
                        for kind in ("html", "audio")
                    ]
                    retry = max([self.clock() + 300] + [row.get("retry_at", 0) for row in rows])
                    self._set_job(
                        job["id"], "queued", retry_at=retry, error=str(error), failure=failure
                    )
                    if isinstance(error, (DikiTimeout, DikiServerError)):
                        count = self.resources.setting("remote_server_errors", 0) + 1
                        self.resources.set_setting("remote_server_errors", count)
                        if count >= 3:
                            self.resources._cooldown(
                                min(300 * 2 ** min(count - 3, 5), 3600),
                                "Repeated upstream failures",
                            )
                    if self.resources.pause_message():
                        break
                except (OSError, ValueError):
                    self._set_job(
                        job["id"],
                        "queued",
                        retry_at=self.clock() + 300,
                        error="Storage/validation failure",
                    )
                    raise PauseWork(
                        "Storage/validation failure; inspect the persistent volume",
                        self.clock() + 300,
                    ) from None
                except Exception:
                    self._set_job(
                        job["id"],
                        "queued",
                        retry_at=self.clock() + 300,
                        error="Unexpected worker failure",
                        failure=True,
                    )
                    raise
            self._state(
                "paused" if self.resources.pause_message() else "idle",
                self.resources.pause_message(),
            )
        except (PauseWork, Deferred, BatchDeadline) as error:
            self._state("paused", str(error))
        finally:
            self.resources.deadline = None
            try:
                with self.resources.db() as db:
                    if job is not None:
                        db.execute(
                            """UPDATE remote_jobs SET state='queued',retry_at=?,error='Interrupted cycle'
                            WHERE id=? AND state='running'""",
                            (self.clock() + 300, job["id"]),
                        )
                    if reservation:
                        day, seconds = reservation
                        elapsed = min(seconds, max(0, self.monotonic() - started))
                        db.execute(
                            "UPDATE remote_usage SET work_seconds=MAX(0,work_seconds-?) WHERE day=?",
                            (seconds - elapsed, day),
                        )
            finally:
                self.cycle_lock.release()

    def _needs_audio(self, job_id):
        with self.resources.db() as db:
            return bool(
                db.execute("SELECT need_audio FROM remote_jobs WHERE id=?", (job_id,)).fetchone()[0]
            )

    def begin_drain(self):
        with self.lock, self.resources.db() as db:
            db.execute("BEGIN IMMEDIATE")
            # One personal consumer. A new launch supersedes abandoned snapshots,
            # never their jobs, manifests, or receipts.
            db.execute("DELETE FROM remote_drain_jobs")
            db.execute("DELETE FROM remote_drains")
            identifier = uuid.uuid4().hex
            db.execute("INSERT INTO remote_drains VALUES (?,?)", (identifier, self.clock()))
            db.execute(
                "INSERT INTO remote_drain_jobs SELECT ?,id FROM remote_jobs WHERE state='ready'",
                (identifier,),
            )
            count = db.execute(
                "SELECT COUNT(*) FROM remote_drain_jobs WHERE drain_id=?", (identifier,)
            ).fetchone()[0]
        return {"id": identifier, "words": count}

    def next_transfer(self, *, drain_id=None):
        with self.lock, self.resources.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                drain_id is not None
                and not db.execute("SELECT 1 FROM remote_drains WHERE id=?", (drain_id,)).fetchone()
            ):
                raise QueueConflict("Unknown startup drain; begin a new startup snapshot")
            previous = db.execute(
                """SELECT envelope FROM remote_batches b WHERE acknowledged=0
                AND (? IS NULL OR EXISTS (SELECT 1 FROM remote_jobs j JOIN remote_drain_jobs d
                    ON d.job_id=j.id WHERE d.drain_id=? AND j.batch_id=b.id))
                ORDER BY created_at LIMIT 1""",
                (drain_id, drain_id),
            ).fetchone()
            if previous:
                return stored_envelope(previous[0])
            items, size = [], 0
            batch_id = uuid.uuid4().hex
            for job in db.execute(
                """SELECT * FROM remote_jobs WHERE state='ready' AND batch_id IS NULL
                AND (? IS NULL OR id IN (SELECT job_id FROM remote_drain_jobs WHERE drain_id=?))
                ORDER BY priority,created_at,rowid LIMIT ?""",
                (drain_id, drain_id, MAX_ITEMS),
            ):
                artifacts = json.loads(job["artifacts"])
                item_size = sum(artifact["size"] for artifact in artifacts)
                if size + item_size > MAX_TRANSFER_BYTES:
                    break
                item = {
                    "id": job["id"],
                    "word": job["word"],
                    "audioState": job["audio_state"],
                    "audioDiscoveryVersion": DISCOVERY_VERSION,
                    "resources": artifacts,
                }
                if job["audio_plan"]:
                    item["audioPlan"] = json.loads(job["audio_plan"])
                candidate = {
                    "manifest": {"protocol": PROTOCOL, "id": batch_id, "items": items + [item]},
                    "digest": "0" * 64,
                }
                if len(canonical(candidate)) > MAX_MANIFEST_BYTES:
                    break
                items.append(item)
                size += item_size
            if not items:
                return None
            manifest = {"protocol": PROTOCOL, "id": batch_id, "items": items}
            envelope = {"manifest": manifest, "digest": digest(manifest)}
            validate_manifest(envelope)
            db.execute(
                "INSERT INTO remote_batches(id,envelope,created_at) VALUES (?,?,?)",
                (manifest["id"], canonical(envelope).decode(), self.clock()),
            )
            for item in items:
                db.execute(
                    "UPDATE remote_jobs SET batch_id=? WHERE id=?", (manifest["id"], item["id"])
                )
            return envelope

    def blob(self, batch_id, job_id, kind):
        with self.lock, self.resources.db() as db:
            row = db.execute(
                "SELECT * FROM remote_batches WHERE id=? AND acknowledged=0", (batch_id,)
            ).fetchone()
            if row is None:
                raise QueueConflict("Transfer is missing or already acknowledged")
            manifest = stored_envelope(row["envelope"])["manifest"]
            for item in manifest["items"]:
                if item["id"] != job_id:
                    continue
                for artifact in item["resources"]:
                    if artifact["kind"] == kind:
                        data = self.resources._cached(item["word"], kind)
                        if data is None:
                            raise QueueConflict(
                                "Stored artifact missing/corrupt; no automatic redownload was attempted"
                            )
                        try:
                            validate_artifact(artifact, data, item["word"])
                        except ValueError:
                            raise QueueConflict(
                                "Stored artifact changed; no automatic redownload was attempted"
                            ) from None
                        return data
            raise QueueConflict("Resource is not part of this transfer")

    def acknowledge(self, batch_id, manifest_digest):
        with self.lock:
            with self.resources.db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM remote_batches WHERE id=?", (batch_id,)).fetchone()
                if not row or stored_envelope(row["envelope"])["digest"] != manifest_digest:
                    raise QueueConflict("Unknown transfer or mismatched receipt")
                db.execute("UPDATE remote_batches SET acknowledged=1 WHERE id=?", (batch_id,))
                db.execute(
                    "UPDATE remote_jobs SET state='delivered',updated_at=? WHERE batch_id=? AND state='ready'",
                    (self.clock(), batch_id),
                )
            self._cleanup_delivered()
            with self.resources.db() as db:
                pending = db.execute(
                    "SELECT COUNT(*) FROM remote_jobs WHERE batch_id=? AND cleaned=0", (batch_id,)
                ).fetchone()[0]
            return {"acknowledged": True, "cleanupPending": pending}

    def _cleanup_delivered(self):
        with self.resources.db() as db:
            jobs = db.execute(
                "SELECT id,word,followup FROM remote_jobs WHERE state='delivered' AND cleaned=0"
            ).fetchall()
        for job in jobs:
            try:
                with file_lock(self.config.data_dir / "cache.lock"):
                    if job["followup"]:
                        followup = json.loads(job["followup"])
                        with self.resources.db() as db:
                            # Reuse HTML only after the old receipt was committed.
                            db.execute(
                                """UPDATE remote_jobs SET id=?,state='queued',need_audio=1,
                                created_at=?,updated_at=?,retry_at=0,attempts=0,error=NULL,
                                audio_state=NULL,artifacts=NULL,batch_id=NULL,followup=NULL,
                                audio_plan=?,priority=? WHERE id=?""",
                                (
                                    uuid.uuid4().hex,
                                    self.clock(),
                                    self.clock(),
                                    canonical(followup["audio_plan"]).decode()
                                    if followup["audio_plan"] is not None
                                    else None,
                                    followup["priority"],
                                    job["id"],
                                ),
                            )
                        self.wake.set()
                        continue
                    for kind in ("html", "audio"):
                        self.resources.path(job["word"], kind).unlink(missing_ok=True)
                        directory = os.open(self.config.data_dir / kind, os.O_RDONLY)
                        try:
                            os.fsync(directory)
                        finally:
                            os.close(directory)
                    with self.resources.db() as db:
                        db.execute("DELETE FROM resources WHERE word=?", (job["word"],))
                        db.execute("DELETE FROM audio_discovery WHERE word=?", (job["word"],))
                        db.execute("DELETE FROM resource_failures WHERE word=?", (job["word"],))
                        db.execute("UPDATE remote_jobs SET cleaned=1 WHERE id=?", (job["id"],))
            except OSError:
                log.exception("Deferred cleanup of acknowledged download")

    def status(self):
        day, tomorrow = self._day()
        with self.resources.db() as db:
            jobs = dict(
                db.execute("SELECT state,COUNT(*) FROM remote_jobs GROUP BY state").fetchall()
            )
            usage = db.execute("SELECT * FROM remote_usage WHERE day=?", (day,)).fetchone()
            used_bytes = db.execute(
                "SELECT COALESCE(SUM(size),0) FROM resources WHERE digest IS NOT NULL"
            ).fetchone()[0]
            failed = [
                dict(row)
                for row in db.execute(
                    "SELECT word,attempts,error FROM remote_jobs WHERE state='failed' LIMIT 20"
                )
            ]
        return {
            "protocol": PROTOCOL,
            "schedulingVersion": 1,
            "jobs": jobs,
            "state": self.resources.setting("remote_state"),
            "requestsToday": usage["requests"] if usage else 0,
            "requestLimit": self.config.requests_per_day,
            "budgetResetsAt": tomorrow,
            "workSecondsToday": usage["work_seconds"] if usage else 0,
            "workSecondsLimit": self.config.work_seconds_per_day,
            "storedBytes": used_bytes,
            "storageLimit": self.config.pending_bytes,
            "cooldownUntil": self.resources.setting("cooldown_until", 0),
            "failedWords": failed,
        }

    def start(self):
        lock = file_lock(self.config.data_dir / "remote-worker.lock", blocking=False)
        lock.__enter__()
        self.worker_lock = lock
        with self.lock, self.resources.db() as db:
            db.execute(
                """UPDATE remote_jobs SET state=CASE WHEN attempts+1>=? THEN 'failed' ELSE 'queued' END,
                attempts=attempts+1,retry_at=?,error='Previous worker interrupted' WHERE state='running'""",
                (self.config.max_attempts, self.clock() + 300),
            )
        self.thread = threading.Thread(target=self._loop, name="diki-downloader", daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stop_event.is_set():
            self.wake.clear()
            try:
                self.run_cycle()
            except Exception:
                # Unexpected failures stop this cycle instead of a hot retry loop.
                log.exception("Remote download cycle stopped unexpectedly")
            self.wake.wait(self.config.poll_seconds)

    def close(self):
        self.stop_event.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=30)
            if self.thread.is_alive():
                # Keep ownership until process exit if an OS-level operation stalls.
                return
        self.resources.close()
        if self.worker_lock:
            self.worker_lock.__exit__(None, None, None)
            self.worker_lock = None
