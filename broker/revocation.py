"""Session revocation list and global kill switch.

Both persisted to SQLite (same file as audit). Two operations the broker
needs to make fast on every /token/exchange call:
  - is the broker kill switch engaged?
  - has this session_id been revoked?

Both run as one indexed SELECT.
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


KILL_SWITCH_KEY = "kill_switch"


SCHEMA = """
CREATE TABLE IF NOT EXISTS revoked_sessions (
    session_id TEXT PRIMARY KEY,
    revoked_at TEXT NOT NULL,
    revoked_by TEXT,
    reason     TEXT
);
CREATE TABLE IF NOT EXISTS broker_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class RevocationStore:
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

    # ----- revoked sessions ------------------------------------------------

    def revoke_session(
        self,
        session_id: str,
        *,
        revoked_by: str | None = None,
        reason: str | None = None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO revoked_sessions(session_id, revoked_at, revoked_by, reason)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                  revoked_at = excluded.revoked_at,
                  revoked_by = excluded.revoked_by,
                  reason     = excluded.reason
                """,
                (session_id, _utcnow(), revoked_by, reason),
            )

    def unrevoke_session(self, session_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM revoked_sessions WHERE session_id = ?",
                (session_id,),
            )
            return cur.rowcount > 0

    def is_revoked(self, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM revoked_sessions WHERE session_id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
            return row is not None

    def list_revoked(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id FROM revoked_sessions"
            ).fetchall()
            return {r["session_id"] for r in rows}

    # ----- kill switch -----------------------------------------------------

    def is_kill_switch_on(self) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM broker_state WHERE key = ?",
                (KILL_SWITCH_KEY,),
            ).fetchone()
            return row is not None and row["value"] == "on"

    def kill_switch_state(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM broker_state WHERE key = ?",
                (KILL_SWITCH_KEY,),
            ).fetchone()
            return {"engaged": bool(row and row["value"] == "on")}

    def engage_kill_switch(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO broker_state(key, value) VALUES (?, 'on')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (KILL_SWITCH_KEY,),
            )

    def disengage_kill_switch(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM broker_state WHERE key = ?",
                (KILL_SWITCH_KEY,),
            )
