from pathlib import Path

from committee.staleness import session_is_stale
from presenters.committee_presenter import build_committee_view
from repositories.committee_repository import CommitteeRepository
from repositories.graph_repository import GraphRepository
from schemas.committee import CommitteeSeat, CommitteeSession, CommitteeVerdict, SeatRemark

CONFIG = str(Path(__file__).resolve().parent.parent / "config")


def _sess(sid, asset, ct):
    v = CommitteeVerdict(bottom_line="b", whats_changing="w", switch_likelihood="将至", direction="偏多",
                         conviction="中", confidence=0.6, time_horizon="t", catalysts_to_watch=[],
                         invalidation="i", positioning="p", key_disagreements=[], evidence_basis=[])
    return CommitteeSession(id=sid, asset_id=asset, asset_name=asset, level=0.6,
                            seats=[CommitteeSeat(name="A", persona="鹰派")], rounds=1, mode="cross",
                            remarks=[SeatRemark(seat_name="A", persona="鹰派", round=1, critique="c")],
                            verdict=v, created_at=ct)


def test_stale_when_newer_session_same_asset():
    old = _sess("GOLD_1", "GOLD", "2026-06-01T00:00:00Z")
    new = _sess("GOLD_2", "GOLD", "2026-06-08T00:00:00Z")
    assert session_is_stale(old, [old, new], []) is True
    assert session_is_stale(new, [old, new], []) is False


def test_stale_when_newer_driver_shift():
    s = _sess("GOLD_1", "GOLD", "2026-06-01T00:00:00Z")
    shifts = [{"node_id": "GOLD", "at": "2026-06-05T00:00:00Z"}]
    assert session_is_stale(s, [s], shifts) is True


def test_stale_by_ttl():
    s = _sess("GOLD_1", "GOLD", "2026-06-01T00:00:00Z")
    assert session_is_stale(s, [s], [], ttl_hours=24, now="2026-06-03T00:00:00Z") is True
    assert session_is_stale(s, [s], [], ttl_hours=24, now="2026-06-01T06:00:00Z") is False


def test_presenter_marks_stale_ids(tmp_path):
    g = GraphRepository(tmp_path, CONFIG); g.seed_if_empty()
    from graph.driver_shift import DriverShift
    g.save_driver_shift(DriverShift(node_id="GOLD", from_driver="a", to_driver="b", at="2026-06-09T00:00:00Z"))
    c = CommitteeRepository(tmp_path, CONFIG)
    c.save_session(_sess("GOLD_1", "GOLD", "2026-06-01T00:00:00Z"))
    view = build_committee_view(c, graph_repo=g)
    assert "GOLD_1" in view.stale_session_ids
