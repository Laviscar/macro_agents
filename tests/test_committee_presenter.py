from pathlib import Path

from presenters.committee_presenter import build_committee_view, estimate_calls
from repositories.committee_repository import CommitteeRepository
from schemas.committee import PendingConvocation

CONFIG = str(Path(__file__).resolve().parent.parent / "config")


def test_view_has_pending_history_config(tmp_path):
    repo = CommitteeRepository(tmp_path, CONFIG)
    repo.save_pending(PendingConvocation(asset_id="GOLD", asset_name="黄金", trigger="velocity",
                      velocity_delta=0.2, ratio=0.5, leader="实际利率", runner_up="央行购金",
                      is_reversal=True, created_at="t"))
    v = build_committee_view(repo)
    assert v.pending and v.pending[0].asset_id == "GOLD"
    assert len(v.skill_library) == 13 and v.default_seats and v.personas


def test_estimate_calls_seats_times_rounds_plus_chair():
    assert estimate_calls(seats=3, rounds=2) == 3 * 2 + 1
