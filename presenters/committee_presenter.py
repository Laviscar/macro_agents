from __future__ import annotations

from committee.staleness import session_is_stale
from view_models.committee_view import CommitteeView


def build_committee_view(committee_repo, graph_repo=None, ttl_hours: float | None = None) -> CommitteeView:
    sessions = committee_repo.list_sessions()
    stale_ids: list[str] = []
    if graph_repo is not None:
        shifts = graph_repo.list_driver_shifts()
        stale_ids = [s.id for s in sessions if session_is_stale(s, sessions, shifts, ttl_hours=ttl_hours)]
    return CommitteeView(
        pending=committee_repo.list_pending(),
        sessions=sessions,
        skill_library=committee_repo.skill_library(),
        default_seats=committee_repo.default_seats(),
        templates=committee_repo.templates(),
        personas=committee_repo.personas(),
        default_rounds=committee_repo.default_rounds(),
        default_mode=committee_repo.default_mode(),
        stale_session_ids=stale_ids,
    )


def estimate_calls(seats: int, rounds: int) -> int:
    """召开一次圆桌的预估 LLM 调用次数:席位 × 轮次 + 1(主席综合)。"""
    return seats * rounds + 1
