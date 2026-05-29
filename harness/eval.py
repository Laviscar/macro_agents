from __future__ import annotations

from dataclasses import dataclass

from harness.metrics import EvalMetrics, compute_metrics
from harness.session_store import HarnessSessionStore


@dataclass(frozen=True)
class EvalReport:
    run_id: str
    window_start: str
    window_end: str
    session_count: int
    metrics: dict


class EvalScheduler:
    def __init__(self, session_store: HarnessSessionStore) -> None:
        self._store = session_store

    def run_eval(self, window_start: str, window_end: str) -> EvalReport:
        all_sessions = self._store.list_sessions(limit=10000)
        in_window = [
            s for s in all_sessions
            if s["status"] == "completed"
            and window_start <= s["created_at"] <= window_end
        ]

        events_by_session: dict[str, list[dict]] = {
            s["id"]: self._store.list_events_for_session(s["id"])
            for s in in_window
        }

        metrics: EvalMetrics = compute_metrics(
            sessions=in_window,
            events_by_session=events_by_session,
        )

        metrics_dict = {
            "narrative_stability": metrics.narrative_stability,
            "evidence_precision": metrics.evidence_precision,
            "challenge_hit_rate": metrics.challenge_hit_rate,
            "latency_seconds": metrics.latency_seconds,
            "tokens_used": metrics.tokens_used,
        }

        run_id = self._store.save_eval_run(
            window_start=window_start,
            window_end=window_end,
            session_count=metrics.session_count,
            metrics=metrics_dict,
        )

        return EvalReport(
            run_id=run_id,
            window_start=window_start,
            window_end=window_end,
            session_count=metrics.session_count,
            metrics=metrics_dict,
        )
