import json
import pytest
from harness.metrics import EvalMetrics, compute_metrics


def _session(narrative_id: str = "main_default") -> dict:
    return {
        "result_json": json.dumps({"main_narrative_id": narrative_id, "stop_reason": "task_complete"}),
        "status": "completed",
    }


def _observe_event(evidence_count: int = 3, avg_confidence: float = 0.8) -> dict:
    return {
        "event_type": "observe_result",
        "payload_json": json.dumps({"evidence_count": evidence_count, "avg_confidence": avg_confidence, "all_skipped": False}),
    }


def _budget_event(elapsed: float = 1.5, tokens: int = 0) -> dict:
    return {
        "event_type": "budget_check",
        "payload_json": json.dumps({"ok": True, "elapsed_seconds": elapsed, "tokens_used": tokens}),
    }


def _plan_event(planned_tools: list | None = None) -> dict:
    return {
        "event_type": "plan_decided",
        "payload_json": json.dumps({"planned_tools": planned_tools or ["sort_and_analyze"]}),
    }


def test_compute_metrics_empty_returns_zeros():
    result = compute_metrics(sessions=[], events_by_session={})
    assert isinstance(result, EvalMetrics)
    assert result.session_count == 0
    assert result.narrative_stability == 0.0
    assert result.evidence_precision == 0.0
    assert result.challenge_hit_rate == 0.0
    assert result.latency_seconds == 0.0
    assert result.tokens_used == 0


def test_narrative_stability_same_id():
    sessions = [_session("main_default"), _session("main_default")]
    result = compute_metrics(sessions=sessions, events_by_session={})
    assert result.narrative_stability == 1.0


def test_narrative_stability_different_id():
    sessions = [_session("main_v1"), _session("main_v2")]
    result = compute_metrics(sessions=sessions, events_by_session={})
    assert result.narrative_stability == 0.0


def test_narrative_stability_single_session():
    sessions = [_session("main_default")]
    result = compute_metrics(sessions=sessions, events_by_session={})
    assert result.narrative_stability == 1.0


def test_evidence_precision_high_confidence():
    sessions = [_session()]
    events = {"s1": [_observe_event(evidence_count=4, avg_confidence=0.9)]}
    result = compute_metrics(sessions=sessions, events_by_session=events)
    assert result.evidence_precision == 1.0


def test_evidence_precision_low_confidence():
    sessions = [_session()]
    events = {"s1": [_observe_event(evidence_count=4, avg_confidence=0.4)]}
    result = compute_metrics(sessions=sessions, events_by_session=events)
    assert result.evidence_precision == 0.0


def test_challenge_hit_rate_with_evidence():
    events = {"s1": [_plan_event(["sort_and_analyze"]), _observe_event(evidence_count=2)]}
    result = compute_metrics(sessions=[_session()], events_by_session=events)
    assert result.challenge_hit_rate == 1.0


def test_challenge_hit_rate_no_evidence():
    events = {"s1": [_plan_event(["sort_and_analyze"]), _observe_event(evidence_count=0)]}
    result = compute_metrics(sessions=[_session()], events_by_session=events)
    assert result.challenge_hit_rate == 0.0


def test_latency_averages_across_sessions():
    events = {
        "s1": [_budget_event(elapsed=2.0)],
        "s2": [_budget_event(elapsed=4.0)],
    }
    result = compute_metrics(sessions=[_session(), _session()], events_by_session=events)
    assert abs(result.latency_seconds - 3.0) < 0.01


def test_tokens_used_sums_across_sessions():
    events = {
        "s1": [_budget_event(tokens=100)],
        "s2": [_budget_event(tokens=200)],
    }
    result = compute_metrics(sessions=[_session(), _session()], events_by_session=events)
    assert result.tokens_used == 300
