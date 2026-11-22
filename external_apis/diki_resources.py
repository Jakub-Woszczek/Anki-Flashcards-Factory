"""Persistent, cache-first Diki resources shared by the app and prefetch process."""

import fcntl
import hashlib
import json
import os
import random
import re
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import ReadTimeoutError

from backend.settings import data_path, diki_cache_directory
from external_apis.diki_audio import DISCOVERY_VERSION, discover_audio_urls

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
TIMEOUT = 15
BLOCK_COOLDOWN = 6 * 60 * 60
RECOVERY_SUCCESSES = 10
MAX_PACING_MULTIPLIER = 16


def normalize_word(word: str) -> str:
    # Query identity is case-preserving: Polish/polish can select different entries.
    word = " ".join(word.split())
    if not word or len(word) > 500 or "\0" in word:
        raise ValueError("Provide a nonempty word or phrase of at most 500 characters")
    return word


class ResourceError(Exception):
    pass


class CacheMiss(ResourceError):
    pass


class Deferred(ResourceError):
    pass


class Blocked(Deferred):
    pass


class BatchDeadline(ResourceError):
    pass


class NoAudio(ResourceError):
    pass


class DikiTimeout(ResourceError):
    """One response stalled; other words may still be available."""


class DikiServerError(ResourceError):
    """An upstream server error, distinct from an anti-bot denial."""


@contextmanager
def file_lock(path: Path, *, blocking=True, deadline=None, clock=time.time, sleep=time.sleep):
    """flock also serializes separate file descriptors in backend worker threads."""
    with path.open("a+b") as handle:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not blocking:
                    raise
                if deadline is not None and clock() >= deadline:
                    # Preserve the lock failure as implicit context, as before.
                    raise BatchDeadline("Batch time limit reached while waiting for Diki")  # noqa: B904
                sleep(0.2)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class DikiResources:
    def __init__(
        self,
        root=None,
        *,
        offline=None,
        deadline=None,
        clock=time.time,
        sleep=time.sleep,
        uniform=random.uniform,
        interval=None,
        jitter=None,
        get=None,
        profile="interactive",
    ):
        if profile not in {"interactive", "background"}:
            raise ValueError("Unknown Diki fetch profile")
        self.profile = profile
        self.root = data_path(root) if root is not None else diki_cache_directory()
        self.offline = (
            os.getenv("DIKI_OFFLINE", "").lower() in {"1", "true", "yes"}
            if offline is None
            else offline
        )
        self.deadline = deadline
        self.clock, self.sleep, self.uniform = clock, sleep, uniform
        self.interval = float(
            interval
            if interval is not None
            else os.getenv("DIKI_BACKGROUND_INTERVAL_SECONDS", "20")
            if profile == "background"
            else 0
        )
        if not 0 <= self.interval <= 3600:
            raise ValueError("Diki request interval must be between 0 and 3600 seconds")
        self.jitter = min(
            max(
                float(
                    jitter if jitter is not None else os.getenv("DIKI_REQUEST_JITTER_SECONDS", "5")
                ),
                0,
            ),
            self.interval,
        )
        self.get = get
        self.session = requests.Session()
        for directory in (self.root, self.root / "html", self.root / "audio"):
            directory.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS resources (
                    word TEXT NOT NULL, kind TEXT NOT NULL, state TEXT NOT NULL,
                    digest TEXT, size INTEGER, status INTEGER, source TEXT,
                    exact_match INTEGER NOT NULL DEFAULT 0, downloaded_at REAL,
                    error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                    retry_at REAL NOT NULL DEFAULT 0, cursor INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(word, kind)
                );
                CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS resource_failures (
                    profile TEXT NOT NULL, word TEXT NOT NULL, kind TEXT NOT NULL,
                    error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                    retry_at REAL NOT NULL DEFAULT 0, cursor INTEGER NOT NULL DEFAULT 0,
                    plan_digest TEXT, PRIMARY KEY(profile, word, kind)
                );
                CREATE TABLE IF NOT EXISTS audio_discovery (
                    word TEXT PRIMARY KEY, version INTEGER NOT NULL,
                    html_digest TEXT NOT NULL, urls TEXT NOT NULL,
                    exhausted INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS request_events (
                    id INTEGER PRIMARY KEY, profile TEXT NOT NULL,
                    occurred_at REAL NOT NULL, details TEXT NOT NULL
                );
            """)
            db.execute("BEGIN IMMEDIATE")
            # Old global network state belongs to the scraper, not interactive use.
            # Keep good files and legacy negative audio rows; discovery revisits them.
            if not db.execute("SELECT 1 FROM settings WHERE name='fetch_profiles_v1'").fetchone():
                db.execute("""INSERT OR IGNORE INTO settings(name,value)
                    SELECT 'background:' || name,value FROM settings
                    WHERE name IN ('cooldown_until','cooldown_reason','next_request_at','last_run')""")
                db.execute("""INSERT OR IGNORE INTO resource_failures
                    (profile,word,kind,error,attempts,retry_at,cursor)
                    SELECT 'background',word,kind,error,attempts,retry_at,cursor
                    FROM resources WHERE error IS NOT NULL OR cursor > 0""")
                db.execute("UPDATE resources SET error=NULL,attempts=0,retry_at=0,cursor=0")
                db.execute("INSERT INTO settings VALUES ('fetch_profiles_v1','true')")

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def request_lock(self):
        return self.root / f"request-{self.profile}.lock"

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.root / "index.sqlite3", timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def setting(self, name, default=None, *, profile=None) -> Any:
        """Read heterogeneous JSON settings (numbers, strings, or request records)."""
        key = f"{profile or self.profile}:{name}"
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE name=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, name, value, *, profile=None):
        key = f"{profile or self.profile}:{name}"
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))

    @staticmethod
    def _resource_view(row, failure=None, discovery=None, html_digest=None):
        result = dict(row)
        result.update(error=None, attempts=0, retry_at=0, cursor=0, plan_digest=None)
        if failure:
            result.update(
                {
                    key: failure[key]
                    for key in ("error", "attempts", "retry_at", "cursor", "plan_digest")
                }
            )
        if result["digest"]:
            result["state"] = "ready"
        elif (
            result["kind"] == "audio"
            and discovery
            and discovery["version"] == DISCOVERY_VERSION
            and discovery["html_digest"] == html_digest
            and discovery["exhausted"]
        ):
            result["state"] = "no_audio"
        else:
            result["state"] = "error" if result["error"] else "pending"
        return result

    def metadata(self, word, kind):
        word = normalize_word(word)
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM resources WHERE word=? AND kind=?", (word, kind)
            ).fetchone()
            failure = db.execute(
                "SELECT * FROM resource_failures WHERE profile=? AND word=? AND kind=?",
                (self.profile, word, kind),
            ).fetchone()
            discovery = db.execute("SELECT * FROM audio_discovery WHERE word=?", (word,)).fetchone()
            html = db.execute(
                "SELECT digest FROM resources WHERE word=? AND kind='html'", (word,)
            ).fetchone()
        return (
            self._resource_view(row, failure, discovery, html[0] if html else None) if row else None
        )

    def path(self, word, kind):
        key = hashlib.sha256(normalize_word(word).encode()).hexdigest()
        return self.root / kind / (key + (".html" if kind == "html" else ".mp3"))

    def _cached(self, word, kind):
        # Readers and writers see a consistent file + digest pair across profiles.
        with file_lock(
            self.root / "cache.lock", deadline=self.deadline, clock=self.clock, sleep=self.sleep
        ):
            return self._read_cached(word, kind)

    def _read_cached(self, word, kind):
        row = self.metadata(word, kind)
        if not row or not row["digest"]:
            return None
        try:
            content = self.path(word, kind).read_bytes()
        except OSError:
            return None
        if hashlib.sha256(content).hexdigest() != row["digest"]:
            return None
        return content

    def _save(self, word, kind, content, status, source, exact=False):
        with file_lock(
            self.root / "cache.lock", deadline=self.deadline, clock=self.clock, sleep=self.sleep
        ):
            self._save_locked(word, kind, content, status, source, exact)

    def _save_locked(self, word, kind, content, status, source, exact):
        path = self.path(word, kind)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".download-")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        with self.db() as db:
            db.execute(
                """INSERT OR REPLACE INTO resources
                (word,kind,state,digest,size,status,source,exact_match,downloaded_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    word,
                    kind,
                    "ready",
                    hashlib.sha256(content).hexdigest(),
                    len(content),
                    status,
                    source,
                    int(exact),
                    self.clock(),
                ),
            )
            db.execute("DELETE FROM resource_failures WHERE word=? AND kind=?", (word, kind))
            if kind == "audio":
                db.execute("UPDATE audio_discovery SET exhausted=0 WHERE word=?", (word,))

    def _failure(self, word, kind, error):
        row = self.metadata(word, kind) or {}
        attempts = row.get("attempts", 0) + 1
        retry = self.clock() + min(1800 * 2 ** min(attempts - 1, 6), 24 * 3600)
        with self.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO resources(word,kind,state) VALUES (?,?,'error')",
                (word, kind),
            )
            db.execute(
                """INSERT INTO resource_failures(profile,word,kind,error,attempts,retry_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(profile,word,kind) DO UPDATE SET
                error=excluded.error,attempts=excluded.attempts,retry_at=excluded.retry_at""",
                (self.profile, word, kind, str(error), attempts, retry),
            )

    def _check_budget(self, wait=0):
        if self.deadline is not None and self.clock() + wait + TIMEOUT >= self.deadline:
            raise BatchDeadline(
                "Batch time limit reached; remaining resources will resume next run"
            )

    def _cooldown(self, seconds, reason):
        until = max(self.setting("cooldown_until", 0), self.clock() + seconds)
        self.set_setting("cooldown_until", until)
        self.set_setting("cooldown_reason", reason)

    def pause_message(self):
        until = self.setting("cooldown_until", 0)
        if until <= self.clock():
            return None
        date = datetime.fromtimestamp(until).astimezone().isoformat(timespec="seconds")
        return (
            f"Diki {self.profile} requests paused until {date}: {self.setting('cooldown_reason')}"
        )

    def _check_pause(self):
        message = self.pause_message()
        if message:
            raise Deferred(message)

    def _interval(self):
        return self.interval * (
            self.setting("pacing_multiplier", 1) if self.profile == "background" else 1
        )

    def _blocked(self, reason, retry_after: float = 0):
        delay = BLOCK_COOLDOWN
        if self.profile == "background":
            strikes = min(self.setting("challenge_streak", 0) + 1, 3)
            self.set_setting("challenge_streak", strikes)
            self.set_setting(
                "pacing_multiplier",
                min(self.setting("pacing_multiplier", 1) * 2, MAX_PACING_MULTIPLIER),
            )
            self.set_setting("success_streak", 0)
            self.set_setting("recovery_pending", True)
            delay = min(BLOCK_COOLDOWN * 2 ** (strikes - 1), 24 * 3600)
        self._cooldown(max(delay, retry_after), reason)

    def _success(self):
        if self.profile != "background":
            return
        # The first successful paced request after a pause is the recovery probe.
        self.set_setting("recovery_pending", False)
        self.set_setting("cooldown_until", 0)
        self.set_setting("cooldown_reason", None)
        streak = self.setting("success_streak", 0) + 1
        if streak >= RECOVERY_SUCCESSES:
            self.set_setting("pacing_multiplier", max(1, self.setting("pacing_multiplier", 1) / 2))
            self.set_setting("challenge_streak", 0)
            streak = 0
        self.set_setting("success_streak", streak)

    def _record_request(self, details):
        self.set_setting("last_request", details)
        counts = self.setting("request_counts", {})
        outcome = details["outcome"]
        counts[outcome] = counts.get(outcome, 0) + 1
        self.set_setting("request_counts", counts)
        with self.db() as db:
            db.execute(
                "INSERT INTO request_events(profile,occurred_at,details) VALUES (?,?,?)",
                (self.profile, self.clock(), json.dumps(details)),
            )
            db.execute(
                "DELETE FROM request_events WHERE id <= (SELECT MAX(id)-1000 FROM request_events)"
            )

    @staticmethod
    def _retry_after(value, now):
        try:
            return max(float(value), 0)
        except (TypeError, ValueError):
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=UTC)
                return max(date.timestamp() - now, 0)
            except (TypeError, ValueError, OverflowError):
                return 0

    def _request(self, url, kind):
        """Caller holds its profile lock through body reads and state updates."""
        self._check_pause()
        wait = max(self.setting("next_request_at", 0) - self.clock(), 0)
        self._check_budget(wait)
        if wait:
            self.sleep(wait)
        self._check_pause()
        # Conservative reservation survives a process killed during the request.
        self.set_setting("next_request_at", self.clock() + TIMEOUT + self._interval() + self.jitter)
        response = None
        started = self.clock()
        details = {
            "url": url,
            "kind": kind,
            "status": None,
            "outcome": "error",
            "recoveryProbe": self.setting("recovery_pending", False),
        }
        try:
            response = (self.get or self.session.get)(
                url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False, stream=True
            )
            status = response.status_code
            # Whitelist diagnostics: never persist cookies, authorization, or bodies.
            details.update(
                status=status,
                headers={
                    key: response.headers[key]
                    for key in ("Content-Type", "Retry-After", "CF-Ray", "CF-Mitigated")
                    if key in response.headers
                },
            )
            if status in {403, 429}:
                details["outcome"] = "rate_limited" if status == 429 else "denied"
                reason = f"Diki returned HTTP {status}; {self.profile} downloads paused"
                self._blocked(
                    reason, self._retry_after(response.headers.get("Retry-After"), self.clock())
                )
                raise Blocked(reason)
            if 500 <= status <= 599:
                details["outcome"] = "server_error"
                delay = self._retry_after(response.headers.get("Retry-After"), self.clock())
                if delay:
                    self._cooldown(delay, f"Diki returned HTTP {status}; respecting Retry-After")
                detail = (
                    " (Cloudflare timed out waiting for Diki's origin server)"
                    if status == 524
                    else ""
                )
                raise DikiServerError(f"Diki returned HTTP {status}{detail}")
            if status not in {200, 404}:
                details["outcome"] = "http_error"
                self._cooldown(
                    max(1800, self._retry_after(response.headers.get("Retry-After"), self.clock())),
                    f"Diki returned HTTP {status}",
                )
                raise ResourceError(f"Diki returned HTTP {status}")
            limit = 10 * 1024 * 1024 if kind == "html" else 5 * 1024 * 1024
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                self._check_budget()
                self.set_setting(
                    "next_request_at", self.clock() + TIMEOUT + self._interval() + self.jitter
                )
                size += len(chunk)
                if size > limit:
                    details["outcome"] = "response_too_large"
                    raise ResourceError("Diki response exceeded the download size limit")
                chunks.append(chunk)
            content = b"".join(chunks)
            mp3 = content.startswith(b"ID3") or (
                len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0
            )
            text = (
                ""
                if kind == "audio" and mp3
                else content[:200000].decode("utf-8", errors="replace").lower()
            )
            markers = (
                "cf-chl-",
                "verify you are human",
                "checking your browser",
                "unusual traffic",
                "access denied",
                "just a moment...",
                "sprawdź, czy jesteś człowiekiem",
            )
            captcha = (
                "captcha" in text
                and "dictionaryentity" not in text
                and "dictionarysuggestions" not in text
            )
            # Real dictionary pages include Cloudflare's JS detection script.
            # Its presence is not itself a challenge or an invalid dictionary.
            soup = (
                BeautifulSoup(content, "html.parser")
                if kind == "html" or content.lstrip().startswith(b"<")
                else None
            )
            # The branch above always creates a soup for HTML resources.
            dictionary_soup = cast(BeautifulSoup, soup)
            dictionary_html = kind == "html" and (
                dictionary_soup.select_one(
                    ".dictionaryEntity, .dictionarySuggestions, .dictionaryNoResults"
                )
                is not None
                or re.search(r"nie znaleziono|brak wyników", dictionary_soup.get_text(), re.I)
                is not None
            )
            title = soup.title.get_text(" ", strip=True)[:200] if soup and soup.title else None
            marker = next((marker for marker in markers if marker in text), None)
            details.update(bytes=size, title=title)
            header_challenge = response.headers.get("CF-Mitigated", "").lower() == "challenge"
            if header_challenge or (not dictionary_html and (captcha or marker)):
                details.update(
                    outcome="challenge",
                    marker="cf-mitigated" if header_challenge else marker or "captcha",
                )
                reason = f"Diki returned an anti-bot challenge; {self.profile} downloads paused"
                self._blocked(
                    reason, self._retry_after(response.headers.get("Retry-After"), self.clock())
                )
                raise Blocked(reason)
            if kind == "html" and not dictionary_html:
                details["outcome"] = "invalid_html"
                self._cooldown(1800, "Unrecognized Diki page; downloads paused")
                raise ResourceError("Diki did not return a recognized dictionary page")
            if kind == "audio" and status == 200 and not mp3:
                details["outcome"] = "invalid_audio"
                self._cooldown(1800, "Invalid Diki MP3 response; downloads paused")
                raise ResourceError("Diki returned invalid MP3 content")
            details["outcome"] = "success" if status == 200 else "not_found"
            self._success()
            return status, content
        except DikiTimeout:
            details["outcome"] = "timeout"
            raise
        except BatchDeadline:
            details["outcome"] = "deadline"
            raise
        except requests.ReadTimeout as error:
            details["outcome"] = "timeout"
            raise DikiTimeout(
                f"Diki ReadTimeout: no response within {TIMEOUT}s; {error}"
            ) from error
        except requests.RequestException as error:
            # Requests wraps streamed-body urllib3 read timeouts in ConnectionError.
            if isinstance(error, requests.ConnectionError) and any(
                isinstance(arg, ReadTimeoutError) for arg in error.args
            ):
                details["outcome"] = "timeout"
                raise DikiTimeout(
                    f"Diki ReadTimeout: response body stalled for {TIMEOUT}s"
                ) from error
            details["outcome"] = "network_error"
            detail = f"Diki {type(error).__name__}: {error}"
            self._cooldown(300, f"{detail}; downloads paused")
            raise ResourceError(f"{detail}; cached words remain available") from error
        finally:
            if response is not None:
                response.close()
            if self.profile == "background" and details["outcome"] not in {"success", "not_found"}:
                self.set_setting("success_streak", 0)
            details["elapsedSeconds"] = round(self.clock() - started, 3)
            self._record_request(details)
            interval = self._interval()
            self.set_setting(
                "next_request_at",
                self.clock() + self.uniform(max(0, interval - self.jitter), interval + self.jitter),
            )

    def _fetch(self, phrase, kind, refresh):
        word = normalize_word(phrase)
        if not refresh:
            cached = self._cached(word, kind)
            if cached is not None and (kind == "html" or self._audio_matches(word)):
                if kind == "html":
                    from external_apis.diki_api import resolve_lookup

                    exact = bool(
                        resolve_lookup(cached.decode("utf-8", errors="replace"), word).meanings
                    )
                    with self.db() as db:
                        db.execute(
                            "UPDATE resources SET exact_match=? WHERE word=? AND kind='html'",
                            (int(exact), word),
                        )
                return cached
            legacy = self._reuse_legacy(word, kind)
            if legacy is not None:
                return legacy
            row = self.metadata(word, kind)
            if row and row["state"] == "no_audio":
                raise NoAudio(f"Diki has no downloadable audio for {phrase}")
        if self.offline:
            raise CacheMiss(f"{phrase}: {kind} is not cached. Download it when online.")
        # Fail promptly before waiting on another request. Rechecked under the lock.
        self._check_pause()
        plan = None
        if kind == "audio":
            # Acquire HTML outside the profile lock (fetch_html uses it too).
            html = self._fetch(word, "html", False)
            plan = self._audio_plan(word, html)
            if (
                not refresh
                and plan["exhausted"]
                and not (self.metadata(word, kind) or {}).get("digest")
            ):
                raise NoAudio(f"Diki has no downloadable audio for {phrase}")
        with file_lock(
            self.request_lock, deadline=self.deadline, clock=self.clock, sleep=self.sleep
        ):
            if not refresh:
                cached = self._cached(word, kind)
                if cached is not None and (kind == "html" or self._audio_matches(word)):
                    return cached
            row = self.metadata(word, kind) or {}
            if not refresh and row.get("state") == "no_audio":
                raise NoAudio(f"Diki has no downloadable audio for {phrase}")
            if not refresh and row.get("retry_at", 0) > self.clock():
                raise Deferred(row.get("error") or "Resource is waiting for its next retry")
            try:
                if kind == "html":
                    return self._download_html(word)
                return self._download_audio(word, row, refresh, plan)
            except (BatchDeadline, NoAudio):
                raise
            except Blocked as error:
                # An actual denied response counts; an already-active pause doesn't.
                self._failure(word, kind, error)
                raise
            except Deferred:
                raise
            except ResourceError as error:
                self._failure(word, kind, error)
                raise

    def _download_html(self, word):
        from external_apis.diki_api import resolve_lookup

        url = "https://www.diki.pl/slownik-angielskiego?" + urlencode({"q": word})
        status, content = self._request(url, "html")
        text = content.decode("utf-8", errors="replace")
        self._save(word, "html", content, status, url, bool(resolve_lookup(text, word).meanings))
        return content

    def _audio_matches(self, word):
        """Old lowercase caches may contain a recording from the other homograph."""
        content = self._cached(word, "html")
        if content is None:
            return False
        row = self.metadata(word, "audio") or {}
        return row.get("source") in discover_audio_urls(
            content.decode("utf-8", errors="replace"), word
        )

    def _reuse_legacy(self, word, kind):
        from external_apis.diki_api import resolve_lookup

        legacy = word.lower()
        if legacy == word:
            return None
        content = self._cached(legacy, "html")
        if content is None:
            return None
        result = resolve_lookup(content.decode("utf-8", errors="replace"), word)
        if not result.meanings or result.case_sensitive:
            return None
        if kind == "audio":
            row = self.metadata(legacy, "audio") or {}
            if row.get("source") not in discover_audio_urls(
                content.decode("utf-8", errors="replace"), word
            ):
                return None
            content = self._cached(legacy, "audio")
            if content is None:
                return None
        row = self.metadata(legacy, kind)
        if row is None:
            return None
        self._save(word, kind, content, row["status"], row["source"], bool(result.meanings))
        return content

    def _audio_plan(self, word, html):
        content = html.encode("utf-8") if isinstance(html, str) else html
        digest = hashlib.sha256(content).hexdigest()
        with (
            file_lock(
                self.root / "cache.lock", deadline=self.deadline, clock=self.clock, sleep=self.sleep
            ),
            self.db() as db,
        ):
            row = db.execute("SELECT * FROM audio_discovery WHERE word=?", (word,)).fetchone()
            if row and row["version"] == DISCOVERY_VERSION and row["html_digest"] == digest:
                return dict(row)
            urls = json.dumps(discover_audio_urls(content.decode("utf-8", errors="replace"), word))
            db.execute(
                "INSERT OR REPLACE INTO audio_discovery VALUES (?,?,?,?,0)",
                (word, DISCOVERY_VERSION, digest, urls),
            )
        return {
            "word": word,
            "version": DISCOVERY_VERSION,
            "html_digest": digest,
            "urls": urls,
            "exhausted": 0,
        }

    def _download_audio(self, word, row, refresh, plan):
        urls = json.loads(plan["urls"])
        plan_digest = hashlib.sha256((plan["html_digest"] + plan["urls"]).encode()).hexdigest()
        cursor = (
            row.get("cursor", 0)
            if not refresh and not row.get("digest") and row.get("plan_digest") == plan_digest
            else 0
        )
        for index in range(cursor, len(urls)):
            status, content = self._request(urls[index], "audio")
            if status == 200:
                self._save(word, "audio", content, status, urls[index])
                return content
            with self.db() as db:
                db.execute(
                    "INSERT OR IGNORE INTO resources(word,kind,state) VALUES (?,'audio','pending')",
                    (word,),
                )
                db.execute(
                    """INSERT INTO resource_failures(profile,word,kind,cursor,plan_digest)
                    VALUES (?,?,'audio',?,?) ON CONFLICT(profile,word,kind) DO UPDATE SET
                    cursor=excluded.cursor,plan_digest=excluded.plan_digest""",
                    (self.profile, word, index + 1, plan_digest),
                )
        with (
            file_lock(
                self.root / "cache.lock", deadline=self.deadline, clock=self.clock, sleep=self.sleep
            ),
            self.db() as db,
        ):
            db.execute(
                "INSERT OR IGNORE INTO resources(word,kind,state) VALUES (?,'audio','pending')",
                (word,),
            )
            db.execute(
                """UPDATE resources SET state=CASE WHEN digest IS NOT NULL THEN 'ready'
                ELSE 'no_audio' END WHERE word=? AND kind='audio'""",
                (word,),
            )
            db.execute(
                """UPDATE audio_discovery SET exhausted=1 WHERE word=? AND html_digest=?""",
                (word, plan["html_digest"]),
            )
            db.execute("DELETE FROM resource_failures WHERE word=? AND kind='audio'", (word,))
        raise NoAudio(f"Diki has no downloadable audio for {word}")

    def fetch_html(self, word, *, refresh=False) -> str:
        from external_apis.diki_api import resolve_lookup

        word = normalize_word(word)
        content = self._fetch(word, "html", refresh)
        text = content.decode("utf-8", errors="replace")
        result = resolve_lookup(text, word)
        # A queued alias and its resolved headword must both work offline. Keep
        # existing independent snapshots; only fill missing canonical resources.
        if result.word and result.meanings and result.word != word:
            if self._cached(result.word, "html") is None:
                row = self.metadata(word, "html")
                if row:
                    self._save(result.word, "html", content, row["status"], row["source"], True)
            audio = self._cached(word, "audio")
            row = self.metadata(word, "audio") or {}
            if (
                audio is not None
                and self._cached(result.word, "audio") is None
                and row.get("source") in discover_audio_urls(text, result.word)
            ):
                self._save(result.word, "audio", audio, row["status"], row["source"])
        return text

    def fetch_audio(self, word, *, refresh=False) -> bytes:
        return self._fetch(word, "audio", refresh)

    def snapshot(self, *, profile=None):
        """Local metadata only; missing/truncated files never count as downloaded."""
        with self.db() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM resources")]
            failures = {
                (row["word"], row["kind"]): dict(row)
                for row in db.execute(
                    "SELECT * FROM resource_failures WHERE profile=?", (profile or self.profile,)
                )
            }
            discoveries = {
                row["word"]: dict(row) for row in db.execute("SELECT * FROM audio_discovery")
            }
        html_digests = {row["word"]: row["digest"] for row in rows if row["kind"] == "html"}
        result = {}
        for row in rows:
            row = self._resource_view(
                row,
                failures.get((row["word"], row["kind"])),
                discoveries.get(row["word"]),
                html_digests.get(row["word"]),
            )
            if row["digest"]:
                content = b""
                try:
                    content = self.path(row["word"], row["kind"]).read_bytes()
                    valid = (
                        len(content) == row["size"]
                        and hashlib.sha256(content).hexdigest() == row["digest"]
                    )
                except OSError:
                    valid = False
                if not valid:
                    row["state"] = "missing"
                elif row["kind"] == "html" and not row["exact_match"]:
                    from external_apis.diki_api import resolve_lookup

                    row["exact_match"] = int(
                        bool(
                            resolve_lookup(
                                content.decode("utf-8", errors="replace"), row["word"]
                            ).meanings
                        )
                    )
            result[(row["word"], row["kind"])] = row
        for (word, kind), row in result.items():
            if kind == "audio" and row["state"] == "ready" and not self._audio_matches(word):
                row["state"] = "pending"
        return result
