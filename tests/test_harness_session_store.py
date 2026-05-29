import json
import pytest
from harness.events import EventType, LoopEvent
from harness.session_store import HarnessSessionStore


@pytest.fixture
def store(tmp_path):
    return HarnessSessionStore(tmp_path / "test.sqlite3")


def test_create_session_returns_id(store):
    session_id = store.create_session(task_description="test task", news_item_ids=[1, 2])
    assert session_id.startswith("sess_")


def test_session_starts_as_running(store):
    session_id = store.create_session()
    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["status"] == "running"
    assert sessions[0]["id"] == session_id


def test_complete_session(store):
    session_id = store.create_session()
    store.complete_session(session_id, {"stop_reason": "task_complete"})
    sessions = store.list_sessions()
    assert sessions[0]["status"] == "completed"
    assert sessions[0]["completed_at"] is not None


def test_fail_session(store):
    session_id = store.create_session()
    store.fail_session(session_id, "something broke")
    sessions = store.list_sessions()
    assert sessions[0]["status"] == "failed"
    result = json.loads(sessions[0]["result_json"])
    assert result["error"] == "something broke"


def test_record_and_list_events(store):
    session_id = store.create_session()
    event = LoopEvent(
        session_id=session_id,
        event_type=EventType.LOOP_TRANSITION,
        state="PLAN",
        payload={"from": "INIT", "to": "PLAN"},
    )
    store.record_event(event)
    events = store.list_events_for_session(session_id)
    assert len(events) == 1
    assert events[0]["event_type"] == "loop_transition"
    assert events[0]["state"] == "PLAN"
    payload = json.loads(events[0]["payload_json"])
    assert payload["to"] == "PLAN"


def test_complete_session_persists_result(store):
    session_id = store.create_session()
    store.complete_session(session_id, {"stop_reason": "task_complete"})
    sessions = store.list_sessions()
    result = json.loads(sessions[0]["result_json"])
    assert result["stop_reason"] == "task_complete"


def test_complete_session_bad_id_raises(store):
    with pytest.raises(KeyError):
        store.complete_session("sess_nonexistent", {})


def test_events_ordered_by_insertion(store):
    session_id = store.create_session()
    for state in ["PLAN", "TOOL_EXEC", "OBSERVE"]:
        store.record_event(LoopEvent(session_id=session_id, event_type=EventType.LOOP_TRANSITION, state=state, payload={}))
    events = store.list_events_for_session(session_id)
    assert [e["state"] for e in events] == ["PLAN", "TOOL_EXEC", "OBSERVE"]


def test_save_and_get_compaction(tmp_path):
    store = HarnessSessionStore(tmp_path / "test.db")
    sess_id = store.create_session(task_description="test", news_item_ids=[1, 2])
    summary = {"news_processed": 2, "evidence_count": 3, "avg_confidence": 0.85, "narrative_id": "main_default"}
    cid = store.save_compaction(sess_id, event_count=10, summary=summary)
    assert cid.startswith("cmpct")
    result = store.get_compaction(sess_id)
    assert result is not None
    assert result["event_count"] == 10
    assert result["summary"]["evidence_count"] == 3


def test_get_compaction_returns_none_for_missing_session(tmp_path):
    store = HarnessSessionStore(tmp_path / "test.db")
    assert store.get_compaction("nonexistent") is None


def test_save_and_list_eval_runs(tmp_path):
    store = HarnessSessionStore(tmp_path / "test.db")
    metrics = {
        "narrative_stability": 1.0, "evidence_precision": 0.8,
        "challenge_hit_rate": 1.0, "latency_seconds": 1.2, "tokens_used": 0,
    }
    rid = store.save_eval_run("2026-05-01", "2026-05-07", session_count=5, metrics=metrics)
    assert rid.startswith("eval")
    runs = store.list_eval_runs()
    assert len(runs) == 1
    assert runs[0]["metrics"]["narrative_stability"] == 1.0
    assert runs[0]["session_count"] == 5


def test_list_eval_runs_empty(tmp_path):
    store = HarnessSessionStore(tmp_path / "test.db")
    assert store.list_eval_runs() == []


def test_foreign_keys_pragma_enabled(tmp_path):
    store = HarnessSessionStore(tmp_path / "test.db")
    cur = store._conn.execute("PRAGMA foreign_keys")
    assert cur.fetchone()[0] == 1


def test_concurrent_event_writes_are_not_lost(tmp_path):
    import threading
    from harness.events import EventType, LoopEvent
    store = HarnessSessionStore(tmp_path / "test.db")
    sess_id = store.create_session()

    def writer():
        for _ in range(20):
            store.record_event(LoopEvent(
                session_id=sess_id,
                event_type=EventType.LOOP_TRANSITION,
                state="PLAN",
                payload={},
            ))

    threads = [threading.Thread(target=writer) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    events = store.list_events_for_session(sess_id)
    assert len(events) == 100  # 5 threads x 20 events, none lost
