from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from utils.clock import now_iso


class EventType(str, Enum):
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"
    LOOP_TRANSITION = "loop_transition"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    BUDGET_CHECK = "budget_check"


@dataclass
class LoopEvent:
    session_id: str
    event_type: EventType
    state: str
    payload: dict
    created_at: str = field(default_factory=now_iso)
