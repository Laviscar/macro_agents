from __future__ import annotations

from dataclasses import dataclass, field

from schemas.committee import (
    CommitteeSeat,
    CommitteeSession,
    CommitteeSkill,
    CommitteeTemplate,
    PendingConvocation,
)


@dataclass(slots=True)
class CommitteeView:
    pending: list[PendingConvocation] = field(default_factory=list)
    sessions: list[CommitteeSession] = field(default_factory=list)
    skill_library: list[CommitteeSkill] = field(default_factory=list)
    default_seats: list[CommitteeSeat] = field(default_factory=list)
    templates: list[CommitteeTemplate] = field(default_factory=list)
    personas: list[str] = field(default_factory=list)
    default_rounds: int = 1
    default_mode: str = "cross"
    stale_session_ids: list[str] = field(default_factory=list)  # 可能已过时的 session(被取代/局势已变)
