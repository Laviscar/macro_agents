from __future__ import annotations

import json

from harness.events import EventType
from harness.session_store import HarnessSessionStore


class CompactionService:
    def __init__(self, session_store: HarnessSessionStore, threshold: int = 20) -> None:
        self._store = session_store
        self.threshold = threshold

    def should_compact(self, session_id: str) -> bool:
        events = self._store.list_events_for_session(session_id)
        if len(events) < self.threshold:
            return False
        return self._store.get_compaction(session_id) is None

    def compact(self, session_id: str) -> dict:
        events = self._store.list_events_for_session(session_id)
        summary = self._summarize(events)
        self._store.save_compaction(session_id, event_count=len(events), summary=summary)
        return {"session_id": session_id, "event_count": len(events), "summary": summary}

    def get_compaction(self, session_id: str) -> dict | None:
        return self._store.get_compaction(session_id)

    def _summarize(self, events: list[dict]) -> dict:
        summary: dict = {
            "news_processed": 0,
            "evidence_count": 0,
            "avg_confidence": 0.0,
            "all_skipped": False,
            "stop_reason": None,
            "latency_seconds": 0.0,
            "tokens_used": 0,
        }
        for event in events:
            etype = event["event_type"]
            raw = event.get("payload_json", "{}")
            try:
                payload = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                payload = {}

            if etype == EventType.OBSERVE_RESULT:
                summary["evidence_count"] = payload.get("evidence_count", 0)
                summary["avg_confidence"] = payload.get("avg_confidence", 0.0)
                summary["all_skipped"] = payload.get("all_skipped", False)
            elif etype == EventType.TOOL_RESULT and payload.get("tool") == "sort_and_analyze":
                summary["news_processed"] = payload.get("processed", 0)
            elif etype == EventType.SESSION_COMPLETED:
                summary["stop_reason"] = payload.get("stop_reason")
            elif etype == EventType.BUDGET_CHECK:
                summary["latency_seconds"] = payload.get("elapsed_seconds", 0.0)
                summary["tokens_used"] = payload.get("tokens_used", 0)
        return summary
