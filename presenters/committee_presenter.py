from __future__ import annotations

from view_models.committee_view import CommitteeView


def build_committee_view(committee_repo) -> CommitteeView:
    return CommitteeView(
        pending=committee_repo.list_pending(),
        sessions=committee_repo.list_sessions(),
        skill_library=committee_repo.skill_library(),
        default_seats=committee_repo.default_seats(),
        templates=committee_repo.templates(),
        personas=committee_repo.personas(),
        default_rounds=committee_repo.default_rounds(),
        default_mode=committee_repo.default_mode(),
    )


def estimate_calls(seats: int, rounds: int) -> int:
    """召开一次圆桌的预估 LLM 调用次数:席位 × 轮次 + 1(主席综合)。"""
    return seats * rounds + 1
