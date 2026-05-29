import pytest
from harness.compaction import CompactionService
from harness.events import EventType, LoopEvent
from harness.loop import LoopState
from harness.session_store import HarnessSessionStore


def _make_store(tmp_path) -> HarnessSessionStore:
    return HarnessSessionStore(tmp_path / "test.db")


def _seed_session(store: HarnessSessionStore, n_events: int = 5) -> str:
    sess_id = store.create_session(task_description="test", news_item_ids=[1])
    for _ in range(n_events):
        store.record_event(LoopEvent(
            session_id=sess_id,
            event_type=EventType.LOOP_TRANSITION,
            state=LoopState.PLAN,
            payload={"from": "INIT", "to": "PLAN"},
        ))
    return sess_id


def test_should_compact_below_threshold(tmp_path):
    store = _make_store(tmp_path)
    svc = CompactionService(store, threshold=10)
    sess_id = _seed_session(store, n_events=5)
    assert svc.should_compact(sess_id) is False


def test_should_compact_above_threshold(tmp_path):
    store = _make_store(tmp_path)
    svc = CompactionService(store, threshold=5)
    sess_id = _seed_session(store, n_events=6)
    assert svc.should_compact(sess_id) is True


def test_should_compact_false_if_already_compacted(tmp_path):
    store = _make_store(tmp_path)
    svc = CompactionService(store, threshold=1)
    sess_id = _seed_session(store, n_events=3)
    svc.compact(sess_id)
    assert svc.should_compact(sess_id) is False


def test_compact_returns_result_with_correct_event_count(tmp_path):
    store = _make_store(tmp_path)
    svc = CompactionService(store, threshold=1)
    sess_id = _seed_session(store, n_events=4)
    result = svc.compact(sess_id)
    assert result["event_count"] == 4
    assert result["session_id"] == sess_id
    assert "summary" in result


def test_compact_extracts_observe_result(tmp_path):
    store = _make_store(tmp_path)
    svc = CompactionService(store, threshold=1)
    sess_id = store.create_session(task_description="test", news_item_ids=[1])
    store.record_event(LoopEvent(
        session_id=sess_id,
        event_type=EventType.OBSERVE_RESULT,
        state=LoopState.OBSERVE,
        payload={"evidence_count": 3, "all_skipped": False, "avg_confidence": 0.85},
    ))
    result = svc.compact(sess_id)
    assert result["summary"]["evidence_count"] == 3
    assert result["summary"]["avg_confidence"] == 0.85


def test_compact_persists_to_store(tmp_path):
    store = _make_store(tmp_path)
    svc = CompactionService(store, threshold=1)
    sess_id = _seed_session(store, n_events=2)
    svc.compact(sess_id)
    stored = store.get_compaction(sess_id)
    assert stored is not None
    assert stored["session_id"] == sess_id


def test_get_compaction_returns_none_for_uncompacted(tmp_path):
    store = _make_store(tmp_path)
    svc = CompactionService(store, threshold=1)
    sess_id = _seed_session(store, n_events=2)
    assert svc.get_compaction(sess_id) is None
