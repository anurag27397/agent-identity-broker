"""SQLite-backed audit log.

One table, append-only. Every event has a timestamp, an actor, a session
correlation id, an event type, and event-specific fields. The point is
that you can answer "what did session X do" or "what touched jti Y" in
one query, regardless of which service emitted the event.

Schema is deliberately denormalized so reads are one SELECT.
"""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


logger = logging.getLogger("audit")


SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_sub TEXT,
    actor_username TEXT,
    session_id TEXT,
    jti TEXT,
    audience TEXT,
    scope TEXT,
    method TEXT,
    path TEXT,
    status INTEGER,
    reason TEXT,
    metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_session_id ON audit_events(session_id);
CREATE INDEX IF NOT EXISTS idx_jti        ON audit_events(jti);
CREATE INDEX IF NOT EXISTS idx_ts         ON audit_events(ts);
"""


# Standard event types
LOGIN = "login"
SESSION_MINTED = "session_token_minted"
SCOPED_MINTED = "scoped_token_minted"
SCOPED_DENIED = "scoped_token_denied"
TOOL_CALL = "tool_call"
SESSION_REVOKED = "session_revoked"


class AuditStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, isolation_level=None, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def record(
        self,
        *,
        event_type: str,
        actor_sub: str | None = None,
        actor_username: str | None = None,
        session_id: str | None = None,
        jti: str | None = None,
        audience: str | None = None,
        scope: str | None = None,
        method: str | None = None,
        path: str | None = None,
        status: int | None = None,
        reason: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        row = (
            datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            event_type,
            actor_sub,
            actor_username,
            session_id,
            jti,
            audience,
            scope,
            method,
            path,
            status,
            reason,
            json.dumps(metadata) if metadata else None,
        )
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO audit_events (
                    ts, event_type, actor_sub, actor_username,
                    session_id, jti, audience, scope,
                    method, path, status, reason, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            return cur.lastrowid or 0

    def recent_sessions(self, limit: int = 25) -> list[dict[str, Any]]:
        """Distinct session_ids ordered by their latest event."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    session_id,
                    MAX(ts)              AS last_seen,
                    COUNT(*)             AS event_count,
                    MAX(actor_username)  AS actor_username,
                    SUM(CASE WHEN event_type='scoped_token_denied' THEN 1 ELSE 0 END) AS denials,
                    SUM(CASE WHEN event_type='tool_call' THEN 1 ELSE 0 END) AS tool_calls
                FROM audit_events
                WHERE session_id IS NOT NULL
                GROUP BY session_id
                ORDER BY last_seen DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def events_for_session(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, event_type, actor_sub, actor_username,
                       session_id, jti, audience, scope, method, path,
                       status, reason, metadata
                FROM audit_events
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def all_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
