"""File-backed vocabulary sources with durable current-entry/removal references."""

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.settings import configured_words_to_add_path, database_path
from backend.word_list import atomic_write, list_lock


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def file_identity(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_dev}:{stat.st_ino}:{stat.st_ctime_ns}"


class SourceChanged(ValueError):
    pass


class SessionStore:
    """Persist settings and one entry reference; the file owns pending words/order."""

    def __init__(self, path: Path | None = None, words_dir: Path | None = None):
        self.path = (path or database_path()).resolve()
        self.words_dir = (words_dir or configured_words_to_add_path().parent).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock = threading.RLock()
        self._local = threading.local()
        self._initialize()

    @contextmanager
    def _connect(self):
        with closing(sqlite3.connect(self.path, timeout=30)) as connection:
            connection.row_factory = sqlite3.Row
            with connection:
                yield connection

    @contextmanager
    def lock(self):
        # Serialize current-entry actions across tabs, threads and backend processes.
        with self._thread_lock:
            if getattr(self._local, "locked", False):
                yield
                return
            with list_lock(self.path.with_name(self.path.name + ".queues")):
                self._local.locked = True
                try:
                    yield
                finally:
                    self._local.locked = False

    def _initialize(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, mode TEXT NOT NULL, name TEXT NOT NULL,
                    source TEXT NOT NULL, filter_json TEXT NOT NULL DEFAULT '{}',
                    deck_name TEXT, model_name TEXT,
                    field_mapping_json TEXT NOT NULL DEFAULT '{}',
                    draft_json TEXT NOT NULL DEFAULT '{}',
                    completed_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    source_path TEXT, entry_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS source_resolutions (
                    entry_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    reason TEXT NOT NULL, save_id TEXT, state TEXT NOT NULL,
                    before_hash TEXT NOT NULL, before_size INTEGER NOT NULL,
                    after_hash TEXT NOT NULL, after_size INTEGER NOT NULL,
                    before_identity TEXT NOT NULL, backup_path TEXT NOT NULL,
                    start_offset INTEGER NOT NULL, end_offset INTEGER NOT NULL,
                    original_line BLOB NOT NULL, created_at TEXT NOT NULL
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
            if "source_path" not in columns:
                db.execute("ALTER TABLE sessions ADD COLUMN source_path TEXT")
            if "entry_json" not in columns:
                db.execute("ALTER TABLE sessions ADD COLUMN entry_json TEXT NOT NULL DEFAULT '{}'")
            # The approved migration takes pending vocabulary from the actual file.
            # Reuse the latest legacy main workspace's target settings, not its words.
            legacy = db.execute(
                """SELECT id FROM sessions WHERE mode='add' AND source_path IS NULL
                AND source='words_to_add.txt' ORDER BY updated_at DESC LIMIT 1"""
            ).fetchone()
            existing = db.execute(
                "SELECT id FROM sessions WHERE source_path='words_to_add.txt'"
            ).fetchone()
            if legacy and not existing:
                db.execute(
                    """UPDATE sessions SET source_path='words_to_add.txt',
                    draft_json='{}', entry_json='{}' WHERE id=?""",
                    (legacy["id"],),
                )
            tables = {
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "session_queue" in tables:
                db.execute(
                    """DELETE FROM session_queue WHERE session_id IN
                    (SELECT id FROM sessions WHERE source_path IS NOT NULL)"""
                )
            db.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS source_workspace
                ON sessions(source_path) WHERE source_path IS NOT NULL"""
            )

    def source_path(self, source: str) -> Path:
        path = (self.words_dir / source).resolve()
        if not path.is_relative_to(self.words_dir) or path.suffix != ".txt" or not path.is_file():
            raise SourceChanged(f"Source file is unavailable: {source}")
        return path

    def _discover(self):
        paths = sorted(
            self.words_dir.rglob("*.txt"),
            key=lambda path: (path.name != "words_to_add.txt", path.as_posix().lower()),
        )
        with self._connect() as db:
            for path in paths:
                if not path.resolve().is_relative_to(self.words_dir) or not path.is_file():
                    continue
                source = path.resolve().relative_to(self.words_dir).as_posix()
                now = utc_now()
                db.execute(
                    """INSERT OR IGNORE INTO sessions
                    (id,mode,name,source,source_path,created_at,updated_at)
                    VALUES (?,'add',?,?,?,?,?)""",
                    (str(uuid.uuid4()), source, source, source, now, now),
                )

    @staticmethod
    def _entries(content: bytes) -> list[dict[str, Any]]:
        entries = []
        offset = 0
        for number, line in enumerate(content.splitlines(keepends=True), 1):
            text = line.decode("utf-8")
            if offset == 0:
                text = text.removeprefix("\ufeff")
            word = text.strip()
            if word:
                entries.append(
                    {"word": word, "start": offset, "end": offset + len(line), "line": number}
                )
            offset += len(line)
        return entries

    @staticmethod
    def _matches(content: bytes, digest: str, size: int) -> bool:
        return len(content) >= size and fingerprint(content[:size]) == digest

    def _finalize(self, entry_id: str):
        with self._connect() as db:
            receipt = db.execute(
                "SELECT * FROM source_resolutions WHERE entry_id=?", (entry_id,)
            ).fetchone()
            if receipt is None or receipt["state"] == "consumed":
                return
            db.execute(
                "UPDATE source_resolutions SET state='consumed' WHERE entry_id=?", (entry_id,)
            )
            db.execute(
                """UPDATE sessions SET entry_json='{}',draft_json='{}',
                completed_count=completed_count+1,updated_at=? WHERE id=?""",
                (utc_now(), receipt["session_id"]),
            )

    def _receipt_state(self, receipt, content: bytes, path: Path) -> str:
        before = self._matches(content, receipt["before_hash"], receipt["before_size"])
        after = self._matches(content, receipt["after_hash"], receipt["after_size"])
        if before and file_identity(path) == receipt["before_identity"]:
            return "before"
        if after and not before and file_identity(path) != receipt["before_identity"]:
            return "after"
        if before and not after:
            return "before"
        raise SourceChanged(
            "Source changed during an interrupted removal. Its contents were preserved; "
            "check the source and its recorded backup before retrying."
        )

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self.lock():
            with self._connect() as db:
                row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
                pending = db.execute(
                    "SELECT * FROM source_resolutions WHERE session_id=? AND state='prepared'",
                    (session_id,),
                ).fetchone()
            if row is None or row["source_path"] is None:
                raise KeyError(session_id)
            path = self.source_path(row["source_path"])
            with list_lock(path):
                content = path.read_bytes()
                if pending and self._receipt_state(pending, content, path) == "after":
                    self._finalize(pending["entry_id"])
                    with self._connect() as db:
                        row = db.execute(
                            "SELECT * FROM sessions WHERE id=?", (session_id,)
                        ).fetchone()
                    assert row is not None
                entries = self._entries(content)
                entry = json.loads(row["entry_json"])
                valid = (
                    entry
                    and entries
                    and entries[0]["word"] == entry["word"]
                    and self._matches(content, entry["hash"], entry["size"])
                )
                if not valid:
                    if pending and pending["state"] == "prepared":
                        with self._connect() as db:
                            state = db.execute(
                                "SELECT state FROM source_resolutions WHERE entry_id=?",
                                (pending["entry_id"],),
                            ).fetchone()[0]
                        if state == "prepared":
                            raise SourceChanged(
                                "Source changed; pending removal must be resolved first."
                            )
                    entry = (
                        {
                            **entries[0],
                            "id": str(uuid.uuid4()),
                            "hash": fingerprint(content),
                            "size": len(content),
                        }
                        if entries
                        else {}
                    )
                    with self._connect() as db:
                        db.execute(
                            "UPDATE sessions SET entry_json=?,draft_json='{}' WHERE id=?",
                            (json.dumps(entry), session_id),
                        )
                draft = json.loads(row["draft_json"]) if valid else {}
            return {
                "id": row["id"],
                "mode": "add",
                "name": row["name"],
                "source": row["source_path"],
                "filter": {},
                "deckName": row["deck_name"],
                "modelName": row["model_name"],
                "fieldMapping": json.loads(row["field_mapping_json"]),
                "draft": draft,
                "completedCount": row["completed_count"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "remainingCount": len(entries),
                "current": {"id": entry["id"], "position": entry["line"] - 1, "word": entry["word"]}
                if entry
                else None,
            }

    def require_current(self, session_id: str, entry_id: str | None = None):
        session = self.get_session(session_id)
        if not session["current"] or (
            entry_id is not None and session["current"]["id"] != entry_id
        ):
            raise SourceChanged(
                "The current source entry changed. Reload the source before continuing."
            )
        return session

    def list_sessions(self):
        with self.lock():
            self._discover()
            with self._connect() as db:
                rows = db.execute(
                    """SELECT * FROM sessions WHERE source_path IS NOT NULL
                    ORDER BY source_path != 'words_to_add.txt', source_path COLLATE NOCASE"""
                ).fetchall()
            result = []
            for row in rows:
                summary = {
                    "id": row["id"],
                    "mode": "add",
                    "name": row["name"],
                    "source": row["source_path"],
                    "deckName": row["deck_name"],
                    "modelName": row["model_name"],
                    "completedCount": row["completed_count"],
                    "updatedAt": row["updated_at"],
                    "remainingCount": 0,
                    "sourceError": None,
                }
                try:
                    path = self.source_path(row["source_path"])
                    with list_lock(path):
                        summary["remainingCount"] = len(self._entries(path.read_bytes()))
                except (OSError, UnicodeError, SourceChanged) as error:
                    summary["sourceError"] = str(error)
                result.append(summary)
            return result

    def update_session(
        self, session_id: str, *, deck_name=None, model_name=None, field_mapping=None
    ):
        with self.lock():
            self.get_session(session_id)
            assignments, values = ["updated_at=?"], [utc_now()]
            for column, value in (
                ("deck_name", deck_name),
                ("model_name", model_name),
                (
                    "field_mapping_json",
                    json.dumps(field_mapping) if field_mapping is not None else None,
                ),
            ):
                if value is not None:
                    assignments.append(f"{column}=?")
                    values.append(value)
            with self._connect() as db:
                db.execute(
                    f"UPDATE sessions SET {','.join(assignments)} WHERE id=?", [*values, session_id]
                )
            return self.get_session(session_id)

    def replace_current_draft(
        self, session_id: str, draft: dict[str, Any], entry_id: str | None = None
    ):
        with self.lock():
            current = self.require_current(session_id, entry_id)
            with self._connect() as db:
                db.execute(
                    "UPDATE sessions SET draft_json=?,updated_at=? WHERE id=?",
                    (json.dumps(draft), utc_now(), session_id),
                )
            return self.require_current(session_id, current["current"]["id"])

    def complete_current(self, session_id: str, entry_id: str, *, reason="discard", save_id=None):
        with self.lock():
            with self._connect() as db:
                receipt = db.execute(
                    "SELECT * FROM source_resolutions WHERE entry_id=? AND session_id=?",
                    (entry_id, session_id),
                ).fetchone()
                row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None or row["source_path"] is None:
                raise KeyError(session_id)
            if receipt and receipt["state"] == "consumed":
                return self.get_session(session_id)
            path = self.source_path(row["source_path"])
            with list_lock(path):
                content = path.read_bytes()
                if receipt:
                    if self._receipt_state(receipt, content, path) == "before":
                        atomic_write(
                            path,
                            content[: receipt["start_offset"]] + content[receipt["end_offset"] :],
                        )
                else:
                    entry = json.loads(row["entry_json"])
                    entries = self._entries(content)
                    if (
                        not entry
                        or entry["id"] != entry_id
                        or not entries
                        or entries[0]["word"] != entry["word"]
                        or not self._matches(content, entry["hash"], entry["size"])
                    ):
                        raise SourceChanged(
                            "Source changed before removal. Reload it; no entry was removed."
                        )
                    start, end = entry["start"], entry["end"]
                    # Keep the UTF-8 BOM as file metadata, not part of the removed entry.
                    if start == 0 and content.startswith(b"\xef\xbb\xbf"):
                        start = 3
                    replacement = content[:start] + content[end:]
                    directory = self.path.parent / "archives"
                    directory.mkdir(parents=True, exist_ok=True)
                    backup = directory / f"source-{entry_id}.txt.bak"
                    atomic_write(backup, content)
                    with self._connect() as db:
                        db.execute(
                            """INSERT INTO source_resolutions VALUES
                            (?,?,?,?, 'prepared',?,?,?,?,?,?,?,?,?,?)""",
                            (
                                entry_id,
                                session_id,
                                reason,
                                save_id,
                                fingerprint(content),
                                len(content),
                                fingerprint(replacement),
                                len(replacement),
                                file_identity(path),
                                str(backup),
                                start,
                                end,
                                content[start:end],
                                utc_now(),
                            ),
                        )
                    atomic_write(path, replacement)
                self._finalize(entry_id)
            return self.get_session(session_id)
