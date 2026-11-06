import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.settings import database_path


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SessionStore:
    """Small durable ordered queues for add and existing-card review sessions."""

    def __init__(self, path: Path | None = None):
        self.path = path or database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL CHECK(mode IN ('add', 'review')),
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    filter_json TEXT NOT NULL DEFAULT '{}',
                    deck_name TEXT,
                    model_name TEXT,
                    field_mapping_json TEXT NOT NULL DEFAULT '{}',
                    draft_json TEXT NOT NULL DEFAULT '{}',
                    completed_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    word TEXT,
                    note_id INTEGER,
                    card_id INTEGER,
                    UNIQUE(session_id, position)
                );

                CREATE INDEX IF NOT EXISTS session_queue_current_idx
                    ON session_queue(session_id, position);
                """
            )

    def create_add_session(self, words: list[str], source: str, name: str | None = None) -> dict[str, Any]:
        cleaned_words = [word.strip() for word in words if word.strip()]
        session_id = str(uuid.uuid4())
        now = utc_now()
        session_name = name.strip() if name and name.strip() else f"{source} session"

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (id, mode, name, source, created_at, updated_at)
                VALUES (?, 'add', ?, ?, ?, ?)
                """,
                (session_id, session_name, source, now, now),
            )
            connection.executemany(
                """
                INSERT INTO session_queue (session_id, position, word)
                VALUES (?, ?, ?)
                """,
                [(session_id, position, word) for position, word in enumerate(cleaned_words)],
            )

        return self.get_session(session_id)

    def _row_to_session(self, row: sqlite3.Row, queue: list[dict[str, Any]]) -> dict[str, Any]:
        current = queue[0] if queue else None
        return {
            "id": row["id"],
            "mode": row["mode"],
            "name": row["name"],
            "source": row["source"],
            "filter": json.loads(row["filter_json"]),
            "deckName": row["deck_name"],
            "modelName": row["model_name"],
            "fieldMapping": json.loads(row["field_mapping_json"]),
            "draft": json.loads(row["draft_json"]),
            "completedCount": row["completed_count"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "remainingCount": len(queue),
            "current": current,
            "queue": queue,
        }

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                raise KeyError(session_id)
            queue_rows = connection.execute(
                """
                SELECT id, position, word, note_id, card_id
                FROM session_queue
                WHERE session_id = ?
                ORDER BY position
                """,
                (session_id,),
            ).fetchall()

        queue = [
            {
                "id": queue_row["id"],
                "position": queue_row["position"],
                "word": queue_row["word"],
                "noteId": queue_row["note_id"],
                "cardId": queue_row["card_id"],
            }
            for queue_row in queue_rows
        ]
        return self._row_to_session(row, queue)

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sessions.*, COUNT(session_queue.id) AS remaining_count
                FROM sessions
                LEFT JOIN session_queue ON session_queue.session_id = sessions.id
                GROUP BY sessions.id
                ORDER BY sessions.updated_at DESC
                """
            ).fetchall()

        return [
            {
                "id": row["id"],
                "mode": row["mode"],
                "name": row["name"],
                "source": row["source"],
                "deckName": row["deck_name"],
                "modelName": row["model_name"],
                "completedCount": row["completed_count"],
                "remainingCount": row["remaining_count"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]

    def delete_session(self, session_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            if cursor.rowcount == 0:
                raise KeyError(session_id)
            # Foreign-key enforcement is connection-specific in SQLite. Remove the
            # durable queue explicitly so a deleted session leaves no orphan rows.
            connection.execute("DELETE FROM session_queue WHERE session_id = ?", (session_id,))

    def update_session(
        self,
        session_id: str,
        *,
        deck_name: str | None = None,
        model_name: str | None = None,
        field_mapping: dict[str, Any] | None = None,
        draft: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assignments: list[str] = ["updated_at = ?"]
        values: list[Any] = [utc_now()]
        if deck_name is not None:
            assignments.append("deck_name = ?")
            values.append(deck_name)
        if model_name is not None:
            assignments.append("model_name = ?")
            values.append(model_name)
        if field_mapping is not None:
            assignments.append("field_mapping_json = ?")
            values.append(json.dumps(field_mapping))
        if draft is not None:
            assignments.append("draft_json = ?")
            values.append(json.dumps(draft))
        values.append(session_id)

        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE sessions SET {', '.join(assignments)} WHERE id = ?", values
            )
            if cursor.rowcount == 0:
                raise KeyError(session_id)

        return self.get_session(session_id)

    def replace_current_draft(self, session_id: str, draft: dict[str, Any]) -> dict[str, Any]:
        return self.update_session(session_id, draft=draft)

    def replace_add_queue(self, session_id: str, words: list[str]) -> dict[str, Any]:
        """Replace the remaining add queue while keeping its completed history intact."""
        cleaned_words = [word.strip() for word in words if word.strip()]
        with self._connect() as connection:
            session = connection.execute(
                "SELECT mode, completed_count FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if session is None:
                raise KeyError(session_id)
            if session["mode"] != "add":
                raise ValueError("Only add-word queues can be edited")

            current = connection.execute(
                """
                SELECT word FROM session_queue
                WHERE session_id = ?
                ORDER BY position
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            # A draft belongs only to the current item. It remains valid when
            # that unchanged item stays at the front of the edited queue.
            keep_draft = bool(current and cleaned_words and cleaned_words[0] == current["word"])

            connection.execute("DELETE FROM session_queue WHERE session_id = ?", (session_id,))
            connection.executemany(
                """
                INSERT INTO session_queue (session_id, position, word)
                VALUES (?, ?, ?)
                """,
                [
                    (session_id, session["completed_count"] + position, word)
                    for position, word in enumerate(cleaned_words)
                ],
            )
            if keep_draft:
                connection.execute(
                    "UPDATE sessions SET updated_at = ? WHERE id = ?", (utc_now(), session_id)
                )
            else:
                connection.execute(
                    "UPDATE sessions SET draft_json = '{}', updated_at = ? WHERE id = ?",
                    (utc_now(), session_id),
                )

        return self.get_session(session_id)

    def complete_current(self, session_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            current = connection.execute(
                """
                SELECT id FROM session_queue
                WHERE session_id = ?
                ORDER BY position
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if current is None:
                raise ValueError("Session queue is empty")
            connection.execute("DELETE FROM session_queue WHERE id = ?", (current["id"],))
            connection.execute(
                """
                UPDATE sessions
                SET draft_json = '{}', completed_count = completed_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (utc_now(), session_id),
            )

        return self.get_session(session_id)
