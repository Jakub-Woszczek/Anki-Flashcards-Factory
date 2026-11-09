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
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlencode

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent.parent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
TIMEOUT = 15
BLOCK_COOLDOWN = 6 * 60 * 60


def normalize_word(word: str) -> str:
    word = " ".join(word.lower().split())
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
                    raise BatchDeadline("Batch time limit reached while waiting for Diki")
                sleep(0.2)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class DikiResources:
    def __init__(self, root=None, *, offline=None, deadline=None,
                 clock=time.time, sleep=time.sleep, uniform=random.uniform,
                 interval=20, jitter=None, get=None):
        configured = Path(root or os.getenv("DIKI_CACHE_DIR", "data/diki_cache")).expanduser()
        self.root = configured if configured.is_absolute() else ROOT / configured
        self.offline = (os.getenv("DIKI_OFFLINE", "").lower() in {"1", "true", "yes"}
                        if offline is None else offline)
        self.deadline = deadline
        self.clock, self.sleep, self.uniform = clock, sleep, uniform
        self.interval = interval
        self.jitter = min(max(float(jitter if jitter is not None else
                                   os.getenv("DIKI_REQUEST_JITTER_SECONDS", "5")), 0), interval)
        self.get = get
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
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.root / "index.sqlite3", timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def setting(self, name, default=None):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE name=?", (name,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, name, value):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (name, json.dumps(value)))

    def metadata(self, word, kind):
        with self.db() as db:
            row = db.execute("SELECT * FROM resources WHERE word=? AND kind=?",
                             (normalize_word(word), kind)).fetchone()
        return dict(row) if row else None

    def path(self, word, kind):
        key = hashlib.sha256(normalize_word(word).encode()).hexdigest()
        return self.root / kind / (key + (".html" if kind == "html" else ".mp3"))

    def _cached(self, word, kind):
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
            db.execute("""INSERT OR REPLACE INTO resources
                (word,kind,state,digest,size,status,source,exact_match,downloaded_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                       (word, kind, "ready", hashlib.sha256(content).hexdigest(),
                        len(content), status, source, int(exact), self.clock()))

    def _failure(self, word, kind, error):
        row = self.metadata(word, kind) or {}
        attempts = row.get("attempts", 0) + 1
        retry = self.clock() + min(1800 * 2 ** min(attempts - 1, 6), 24 * 3600)
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO resources(word,kind,state) VALUES (?,?,'error')",
                       (word, kind))
            db.execute("""UPDATE resources SET error=?, attempts=?, retry_at=?,
                state=CASE WHEN digest IS NOT NULL THEN 'ready' ELSE 'error' END
                WHERE word=? AND kind=?""", (str(error), attempts, retry, word, kind))

    def _check_budget(self, wait=0):
        if self.deadline is not None and self.clock() + wait + TIMEOUT >= self.deadline:
            raise BatchDeadline("Batch time limit reached; remaining resources will resume next run")

    def _cooldown(self, seconds, reason):
        until = max(self.setting("cooldown_until", 0), self.clock() + seconds)
        self.set_setting("cooldown_until", until)
        self.set_setting("cooldown_reason", reason)

    @staticmethod
    def _retry_after(value, now):
        try:
            return max(float(value), 0)
        except (TypeError, ValueError):
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                return max(date.timestamp() - now, 0)
            except (TypeError, ValueError, OverflowError):
                return 0

    def _request(self, url, kind):
        """Caller holds request.lock, including through body reads and state updates."""
        if self.setting("cooldown_until", 0) > self.clock():
            raise Deferred(self.setting("cooldown_reason", "Diki requests are cooling down"))
        wait = max(self.setting("next_request_at", 0) - self.clock(), 0)
        self._check_budget(wait)
        if wait:
            self.sleep(wait)
        # Conservative reservation survives a process killed during the request.
        self.set_setting("next_request_at", self.clock() + TIMEOUT + self.interval + self.jitter)
        response = None
        try:
            response = (self.get or requests.get)(url, headers=HEADERS, timeout=TIMEOUT,
                                                 allow_redirects=False, stream=True)
            status = response.status_code
            if status in {403, 429}:
                delay = max(BLOCK_COOLDOWN, self._retry_after(response.headers.get("Retry-After"), self.clock()))
                reason = f"Diki returned HTTP {status}; downloads paused"
                self._cooldown(delay, reason)
                raise Blocked(reason)
            if 500 <= status <= 599:
                delay = self._retry_after(response.headers.get("Retry-After"), self.clock())
                if delay:
                    self._cooldown(delay, f"Diki returned HTTP {status}; respecting Retry-After")
                detail = " (Cloudflare timed out waiting for Diki's origin server)" if status == 524 else ""
                raise DikiServerError(f"Diki returned HTTP {status}{detail}")
            if status not in {200, 404}:
                self._cooldown(max(1800, self._retry_after(response.headers.get("Retry-After"), self.clock())),
                               f"Diki returned HTTP {status}")
                raise ResourceError(f"Diki returned HTTP {status}")
            limit = 10 * 1024 * 1024 if kind == "html" else 5 * 1024 * 1024
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                self._check_budget()
                self.set_setting("next_request_at", self.clock() + TIMEOUT + self.interval + self.jitter)
                size += len(chunk)
                if size > limit:
                    raise ResourceError("Diki response exceeded the download size limit")
                chunks.append(chunk)
            content = b"".join(chunks)
            text = content[:200000].decode("utf-8", errors="replace").lower()
            markers = ("cf-chl-", "challenge-platform", "verify you are human",
                       "checking your browser", "unusual traffic", "access denied",
                       "just a moment...", "sprawdź, czy jesteś człowiekiem")
            captcha = "captcha" in text and "dictionaryentity" not in text and "dictionarysuggestions" not in text
            # Real dictionary pages include Cloudflare's JS detection script.
            # Its presence is not itself a challenge or an invalid dictionary.
            dictionary_html = (kind == "html" and BeautifulSoup(content, "html.parser").select_one(
                ".dictionaryEntity, .dictionarySuggestions, .dictionaryNoResults") is not None)
            if not dictionary_html and (captcha or any(marker in text for marker in markers)):
                reason = "Diki returned an anti-bot challenge; downloads paused"
                self._cooldown(BLOCK_COOLDOWN, reason)
                raise Blocked(reason)
            return status, content
        except requests.ReadTimeout as error:
            raise DikiTimeout(f"Diki ReadTimeout: no response within {TIMEOUT}s; {error}") from error
        except requests.RequestException as error:
            detail = f"Diki {type(error).__name__}: {error}"
            self._cooldown(300, f"{detail}; downloads paused")
            raise ResourceError(f"{detail}; cached words remain available") from error
        finally:
            if response is not None:
                response.close()
            self.set_setting("next_request_at", self.clock() +
                             self.uniform(self.interval - self.jitter, self.interval + self.jitter))

    def _fetch(self, phrase, kind, refresh):
        word = normalize_word(phrase)
        if not refresh:
            cached = self._cached(word, kind)
            if cached is not None:
                return cached
            row = self.metadata(word, kind)
            if row and row["state"] == "no_audio":
                raise NoAudio(f"Diki has no downloadable audio for {phrase}")
        if self.offline:
            raise CacheMiss(f"{phrase}: {kind} is not cached. Download it when online.")
        with file_lock(self.root / "request.lock", deadline=self.deadline,
                       clock=self.clock, sleep=self.sleep):
            if not refresh:
                cached = self._cached(word, kind)
                if cached is not None:
                    return cached
            row = self.metadata(word, kind) or {}
            if not refresh and row.get("state") == "no_audio":
                raise NoAudio(f"Diki has no downloadable audio for {phrase}")
            if not refresh and row.get("retry_at", 0) > self.clock():
                raise Deferred(row.get("error") or "Resource is waiting for its next retry")
            try:
                if kind == "html":
                    return self._download_html(word)
                return self._download_audio(word, row, refresh)
            except (BatchDeadline, NoAudio):
                raise
            except ResourceError as error:
                self._failure(word, kind, error)
                raise

    def _download_html(self, word):
        from external_APIs.dikiApi import parse_meanings

        url = "https://www.diki.pl/slownik-angielskiego?" + urlencode({"q": word})
        status, content = self._request(url, "html")
        text = content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(text, "html.parser")
        if not soup.select_one(".dictionaryEntity, .dictionarySuggestions, .dictionaryNoResults"):
            if not re.search(r"nie znaleziono|brak wyników", soup.get_text(), re.I):
                self._cooldown(1800, "Unrecognized Diki page; downloads paused")
                raise ResourceError("Diki did not return a recognized dictionary page")
        self._save(word, "html", content, status, url, bool(parse_meanings(text, word)))
        return content

    def _download_audio(self, word, row, refresh):
        slug = re.sub(r"[^\w_-]", "", word.replace(" ", "_"))
        urls = [f"https://www.diki.pl/images-common/{lang}/mp3/{quote(slug)}{version}.mp3"
                for lang in ("en", "en-ame") for version in ("", "-v", "-n")]
        # A positive cache record with a missing/corrupt file must re-download,
        # even if a previous explicit refresh exhausted its fallback variants.
        cursor = 0 if refresh or row.get("digest") else row.get("cursor", 0)
        for index in range(cursor, len(urls)):
            status, content = self._request(urls[index], "audio")
            if status == 200:
                # Reject HTML block/error bodies, including those served with HTTP 200.
                if not (content.startswith(b"ID3") or
                        (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0)):
                    self._cooldown(1800, "Invalid Diki MP3 response; downloads paused")
                    raise ResourceError("Diki returned invalid MP3 content")
                self._save(word, "audio", content, status, urls[index])
                return content
            with self.db() as db:
                db.execute("INSERT OR IGNORE INTO resources(word,kind,state) VALUES (?,'audio','pending')", (word,))
                db.execute("UPDATE resources SET cursor=? WHERE word=? AND kind='audio'", (index + 1, word))
        with self.db() as db:
            db.execute("""UPDATE resources SET state=CASE WHEN digest IS NOT NULL THEN 'ready' ELSE 'no_audio' END,
                error=NULL, retry_at=0 WHERE word=? AND kind='audio'""", (word,))
        raise NoAudio(f"Diki has no downloadable audio for {word}")

    def fetch_html(self, word, *, refresh=False) -> str:
        return self._fetch(word, "html", refresh).decode("utf-8", errors="replace")

    def fetch_audio(self, word, *, refresh=False) -> bytes:
        return self._fetch(word, "audio", refresh)

    def snapshot(self):
        """Local metadata only; missing/truncated files never count as downloaded."""
        with self.db() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM resources")]
        result = {}
        for row in rows:
            if row["digest"]:
                try:
                    content = self.path(row["word"], row["kind"]).read_bytes()
                    valid = (len(content) == row["size"] and
                             hashlib.sha256(content).hexdigest() == row["digest"])
                except OSError:
                    valid = False
                if not valid:
                    row["state"] = "missing"
            result[(row["word"], row["kind"])] = row
        return result
