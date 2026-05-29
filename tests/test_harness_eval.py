import pytest
from harness.eval import EvalReport, EvalScheduler
from harness.events import EventType, LoopEvent
from harness.loop import LoopState
from harness.session_store import HarnessSessionStore


def _make_store(tmp_path) -> HarnessSessionStore:
    return HarnessSessionStore(tmp_path / "test.db")


def _seed_completed_session(
    store: HarnessSessionStore,
    narrative_id: str = "main_default",
    evidence_count: int = 2,
) -> str:
    sess_id = store.create_session(task_description="test session", news_item_ids=[1])
    store.record_event(LoopEvent(
        session_id=sess_id, event_type=EventType.PLAN_DECIDED,
        state=LoopState.PLAN,
        payload={"planned_tools": ["sort_and_analyze"], "news_item_count": 1},
    ))
    store.record_event(LoopEvent(
        session_id=sess_id, event_type=EventType.OBSERVE_RESULT,
        state=LoopState.OBSERVE,
        payload={"evidence_count": evidence_count, "all_skipped": False, "avg_confidence": 0.85},
    ))
    store.record_event(LoopEvent(
        session_id=sess_id, event_type=EventType.BUDGET_CHECK,
        state=LoopState.CHECK_BUDGET_AND_STOP,
        payload={"ok": True, "reason": None, "elapsed_seconds": 1.5, "tokens_used": 0},
    ))
    store.complete_session(sess_id, {"main_narrative_id": narrative_id, "stop_reason": "task_complete"})
    return sess_id


def test_run_eval_returns_eval_report(tmp_path):
    store = _make_store(tmp_path)
    _seed_completed_session(store)
    scheduler = EvalScheduler(store)
    report = scheduler.run_eval(window_start="2020-01-01", window_end="2030-01-01")
    assert isinstance(report, EvalReport)
    assert report.session_count >= 1
    assert report.run_id.startswith("eval")


def test_run_eval_no_sessions_returns_zero_metrics(tmp_path):
    store = _make_store(tmp_path)
    scheduler = EvalScheduler(store)
    report = scheduler.run_eval(window_start="2020-01-01", window_end="2020-01-02")
    assert report.session_count == 0
    assert report.metrics["narrative_stability"] == 0.0


def test_run_eval_persists_to_db(tmp_path):
    store = _make_store(tmp_path)
    _seed_completed_session(store)
    scheduler = EvalScheduler(store)
    report = scheduler.run_eval(window_start="2020-01-01", window_end="2030-01-01")
    runs = store.list_eval_runs()
    assert len(runs) == 1
    assert runs[0]["id"] == report.run_id


def test_run_eval_metrics_content(tmp_path):
    store = _make_store(tmp_path)
    _seed_completed_session(store, narrative_id="main_default", evidence_count=3)
    _seed_completed_session(store, narrative_id="main_default", evidence_count=2)
    scheduler = EvalScheduler(store)
    report = scheduler.run_eval(window_start="2020-01-01", window_end="2030-01-01")
    assert report.metrics["narrative_stability"] == 1.0
    assert report.metrics["challenge_hit_rate"] == 1.0
    assert report.metrics["evidence_precision"] == 1.0


def test_run_eval_multiple_calls_accumulate_runs(tmp_path):
    store = _make_store(tmp_path)
    _seed_completed_session(store)
    scheduler = EvalScheduler(store)
    scheduler.run_eval(window_start="2020-01-01", window_end="2030-01-01")
    scheduler.run_eval(window_start="2020-01-01", window_end="2030-01-01")
    assert len(store.list_eval_runs()) == 2
