from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from schemas.analysis_card import AnalysisCard
from schemas.evidence import Evidence
from schemas.raw_news_item import RawNewsItem
from schemas.resource_card import ResourceCard


class SQLiteNewsRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_name TEXT NOT NULL,
                external_id TEXT,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                raw_payload_json TEXT NOT NULL,
                resource_card_json TEXT,
                analysis_status TEXT NOT NULL,
                last_error TEXT
            );

            CREATE TABLE IF NOT EXISTS analysis_cards (
                id TEXT PRIMARY KEY,
                news_item_id INTEGER NOT NULL,
                analysis_card_json TEXT NOT NULL,
                mainline_relation TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(news_item_id) REFERENCES news_items(id)
            );

            CREATE TABLE IF NOT EXISTS evidence_records (
                id TEXT PRIMARY KEY,
                news_item_id INTEGER NOT NULL,
                analysis_card_id TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                target_main_narrative_id TEXT,
                target_branch_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(news_item_id) REFERENCES news_items(id),
                FOREIGN KEY(analysis_card_id) REFERENCES analysis_cards(id)
            );
            """
        )
        self.connection.commit()

    def insert_news_item(self, item: RawNewsItem) -> int:
        dedupe_key = item.build_dedupe_key()
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO news_items (
                source_type,
                source_name,
                external_id,
                url,
                title,
                summary,
                published_at,
                fetched_at,
                dedupe_key,
                raw_payload_json,
                analysis_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.source_type,
                item.source_name,
                item.external_id,
                item.url,
                item.title,
                item.summary,
                item.published_at,
                item.fetched_at,
                dedupe_key,
                json.dumps(item.raw_payload, ensure_ascii=False),
                "pending_sort",
            ),
        )
        self.connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)

        row = self.connection.execute(
            "SELECT id FROM news_items WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        if row is None:
            raise ValueError("Failed to insert or locate news item.")
        return int(row["id"])

    def count_news_items(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM news_items").fetchone()
        return int(row["count"])

    def count_analysis_cards(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM analysis_cards").fetchone()
        return int(row["count"])

    def count_evidence_records(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM evidence_records").fetchone()
        return int(row["count"])

    def list_news_items(self, limit: int = 50) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM news_items
            ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_pending_news(self, limit: int = 20) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM news_items
            WHERE analysis_status IN ('pending_sort', 'pending_analysis')
            ORDER BY COALESCE(published_at, fetched_at) ASC, id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_news_by_status(
        self,
        status: str,
        limit: int = 20,
        since: str | None = None,
        newest_first: bool = False,
    ) -> list[dict]:
        """List news items by status.

        `since` (ISO) keeps only items whose effective time COALESCE(published_at,
        fetched_at) is >= since. `newest_first=True` returns most-recent first (used by
        the manual Run-Now path so it processes fresh news, not the oldest backlog).
        """
        order = "DESC" if newest_first else "ASC"
        where = "analysis_status = ?"
        params: list = [status]
        if since:
            where += " AND COALESCE(published_at, fetched_at) >= ?"
            params.append(since)
        params.append(limit)
        rows = self.connection.execute(
            f"SELECT * FROM news_items WHERE {where} "
            f"ORDER BY COALESCE(published_at, fetched_at) {order}, id {order} LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def get_evidence_since(self, created_after: str) -> list[Evidence]:
        rows = self.connection.execute(
            "SELECT evidence_json FROM evidence_records WHERE created_at > ? ORDER BY created_at ASC",
            (created_after,),
        ).fetchall()
        return [Evidence.model_validate_json(row["evidence_json"]) for row in rows]

    def get_evidence_claims(self, evidence_ids: list[str]) -> dict[str, str]:
        """Map evidence id -> claim text, for resolving narrative supporting/counter IDs to readable text."""
        if not evidence_ids:
            return {}
        placeholders = ",".join("?" * len(evidence_ids))
        rows = self.connection.execute(
            f"SELECT id, evidence_json FROM evidence_records WHERE id IN ({placeholders})",
            list(evidence_ids),
        ).fetchall()
        return {row["id"]: Evidence.model_validate_json(row["evidence_json"]).claim for row in rows}

    def get_analysis_cards_since(self, created_after: str) -> list[AnalysisCard]:
        rows = self.connection.execute(
            "SELECT analysis_card_json FROM analysis_cards WHERE created_at > ? ORDER BY created_at ASC",
            (created_after,),
        ).fetchall()
        return [AnalysisCard.model_validate_json(row["analysis_card_json"]) for row in rows]

    def get_news_item(self, news_item_id: int) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM news_items WHERE id = ?",
            (news_item_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def save_resource_card(self, news_item_id: int, resource_card: ResourceCard, status: str) -> None:
        self.connection.execute(
            """
            UPDATE news_items
            SET resource_card_json = ?, analysis_status = ?, last_error = NULL
            WHERE id = ?
            """,
            (
                resource_card.model_dump_json(),
                status,
                news_item_id,
            ),
        )
        self.connection.commit()

    def save_analysis_bundle(
        self,
        news_item_id: int,
        analysis_card: AnalysisCard,
        evidence_list: list[Evidence],
    ) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO analysis_cards (
                id,
                news_item_id,
                analysis_card_json,
                mainline_relation,
                confidence,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_card.id,
                news_item_id,
                analysis_card.model_dump_json(),
                analysis_card.mainline_relation,
                analysis_card.confidence,
                analysis_card.created_at,
            ),
        )
        for evidence in evidence_list:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO evidence_records (
                    id,
                    news_item_id,
                    analysis_card_id,
                    evidence_json,
                    relation_type,
                    target_main_narrative_id,
                    target_branch_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.id,
                    news_item_id,
                    analysis_card.id,
                    evidence.model_dump_json(),
                    evidence.relation_type,
                    evidence.target_main_narrative_id,
                    evidence.target_branch_id,
                    evidence.created_at,
                ),
            )
        self.connection.execute(
            """
            UPDATE news_items
            SET analysis_status = 'analyzed', last_error = NULL
            WHERE id = ?
            """,
            (news_item_id,),
        )
        self.connection.commit()

    def mark_error(self, news_item_id: int, error_message: str) -> None:
        self.connection.execute(
            """
            UPDATE news_items
            SET analysis_status = 'error', last_error = ?
            WHERE id = ?
            """,
            (error_message, news_item_id),
        )
        self.connection.commit()

    def get_status_counts(self) -> dict[str, int]:
        rows = self.connection.execute(
            """
            SELECT analysis_status, COUNT(*) AS count
            FROM news_items
            GROUP BY analysis_status
            """
        ).fetchall()
        return {str(row["analysis_status"]): int(row["count"]) for row in rows}

    def get_analysis_cards_for_news_item(self, news_item_id: int) -> list[AnalysisCard]:
        rows = self.connection.execute(
            "SELECT analysis_card_json FROM analysis_cards WHERE news_item_id = ? ORDER BY created_at DESC",
            (news_item_id,),
        ).fetchall()
        return [AnalysisCard.model_validate_json(row["analysis_card_json"]) for row in rows]

    def get_evidence_for_news_item(self, news_item_id: int) -> list[Evidence]:
        rows = self.connection.execute(
            "SELECT evidence_json FROM evidence_records WHERE news_item_id = ? ORDER BY created_at DESC",
            (news_item_id,),
        ).fetchall()
        return [Evidence.model_validate_json(row["evidence_json"]) for row in rows]

    def get_latest_analysis_created_at(self) -> str | None:
        row = self.connection.execute(
            "SELECT created_at FROM analysis_cards ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return str(row["created_at"])
