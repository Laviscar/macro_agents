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


def test_events_ordered_by_insertion(store):
    session_id = store.create_session()
    for state in ["PLAN", "TOOL_EXEC", "OBSERVE"]:
        store.record_event(LoopEvent(session_id=session_id, event_type=EventType.LOOP_TRANSITION, state=state, payload={}))
    events = store.list_events_for_session(session_id)
    assert [e["state"] for e in events] == ["PLAN", "TOOL_EXEC", "OBSERVE"]
