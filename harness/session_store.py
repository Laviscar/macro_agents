from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from harness.events import LoopEvent
from utils.clock import now_iso
from utils.ids import new_id


class HarnessSessionStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
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
            CREATE TABLE IF NOT EXISTS harness_compactions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                event_count INTEGER NOT NULL,
                summary_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES harness_sessions(id)
            );
            CREATE TABLE IF NOT EXISTS harness_eval_runs (
                id TEXT PRIMARY KEY,
                window_start_date TEXT NOT NULL,
                window_end_date TEXT NOT NULL,
                session_count INTEGER NOT NULL,
                metrics_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        self._conn.commit()

    def create_session(
        self,
        task_description: str = "",
        news_item_ids: list[int] | None = None,
    ) -> str:
        with self._lock:
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
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE harness_sessions SET status='completed', result_json=?, completed_at=? WHERE id=?",
                (json.dumps(result, ensure_ascii=False), now_iso(), session_id),
            )
            self._conn.commit()
            if cursor.rowcount == 0:
                raise KeyError(f"Session not found: {session_id}")

    def fail_session(self, session_id: str, error: str) -> None:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE harness_sessions SET status='failed', result_json=?, completed_at=? WHERE id=?",
                (json.dumps({"error": error}), now_iso(), session_id),
            )
            self._conn.commit()
            if cursor.rowcount == 0:
                raise KeyError(f"Session not found: {session_id}")

    def record_event(self, event: LoopEvent) -> None:
        with self._lock:
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

    def save_compaction(self, session_id: str, event_count: int, summary: dict) -> str:
        with self._lock:
            compaction_id = new_id("cmpct")
            self._conn.execute(
                "INSERT INTO harness_compactions (id, session_id, event_count, summary_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (compaction_id, session_id, event_count, json.dumps(summary, ensure_ascii=False), now_iso()),
            )
            self._conn.commit()
            return compaction_id

    def get_compaction(self, session_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM harness_compactions WHERE session_id=?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["summary"] = json.loads(d.pop("summary_json"))
        return d

    def save_eval_run(self, window_start: str, window_end: str, session_count: int, metrics: dict) -> str:
        with self._lock:
            run_id = new_id("eval")
            self._conn.execute(
                "INSERT INTO harness_eval_runs (id, window_start_date, window_end_date, session_count, metrics_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, window_start, window_end, session_count, json.dumps(metrics, ensure_ascii=False), now_iso()),
            )
            self._conn.commit()
            return run_id

    def list_eval_runs(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM harness_eval_runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["metrics"] = json.loads(d.pop("metrics_json"))
            result.append(d)
        return result
