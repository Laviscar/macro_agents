from datetime import datetime

from harness.events import EventType, LoopEvent


def test_loop_event_defaults_created_at():
    event = LoopEvent(
        session_id="sess_abc",
        event_type=EventType.LOOP_TRANSITION,
        state="INIT",
        payload={"from": "INIT", "to": "PLAN"},
    )
    assert event.session_id == "sess_abc"
    assert event.event_type == EventType.LOOP_TRANSITION
    assert event.state == "INIT"
    assert isinstance(event.created_at, str)
    assert len(event.created_at) > 0
    datetime.fromisoformat(event.created_at)  # raises if not valid ISO-8601


def test_event_type_values():
    assert EventType.SESSION_STARTED == "session_started"
    assert EventType.TOOL_CALL == "tool_call"
    assert EventType.BUDGET_CHECK == "budget_check"
