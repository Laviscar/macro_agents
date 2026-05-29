from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from harness.events import LoopEvent
from utils.clock import now_iso
from utils.ids import new_id


class HarnessSessionStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS harness_sessions (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                task_description TEXT NOT NULL DEFAULT '',
                news_item_ids_json TEXT NOT NULL DEFAULT '[]',
                result_json TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS harness_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES harness_sessions(id)
            );
        """)
        self._conn.commit()

    def create_session(
        self,
        task_description: str = "",
        news_item_ids: list[int] | None = None,
    ) -> str:
        session_id = new_id("sess")
        self._conn.execute(
            """
            INSERT INTO harness_sessions
                (id, status, task_description, news_item_ids_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, "running", task_description, json.dumps(news_item_ids or []), now_iso()),
        )
        self._conn.commit()
        return session_id

    def complete_session(self, session_id: str, result: dict) -> None:
        self._conn.execute(
            "UPDATE harness_sessions SET status='completed', result_json=?, completed_at=? WHERE id=?",
            (json.dumps(result, ensure_ascii=False), now_iso(), session_id),
        )
        self._conn.commit()

    def fail_session(self, session_id: str, error: str) -> None:
        self._conn.execute(
            "UPDATE harness_sessions SET status='failed', result_json=?, completed_at=? WHERE id=?",
            (json.dumps({"error": error}), now_iso(), session_id),
        )
        self._conn.commit()

    def record_event(self, event: LoopEvent) -> None:
        self._conn.execute(
            """
            INSERT INTO harness_events
                (session_id, event_type, state, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.session_id,
                event.event_type,
                event.state,
                json.dumps(event.payload, ensure_ascii=False, default=str),
                event.created_at,
            ),
        )
        self._conn.commit()

    def list_events_for_session(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM harness_events WHERE session_id=? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_sessions(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM harness_sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
