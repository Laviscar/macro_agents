from pathlib import Path

from repositories.committee_repository import CommitteeRepository
from schemas.committee import (
    CommitteeSeat,
    CommitteeSession,
    CommitteeVerdict,
    PendingConvocation,
    SeatRemark,
)

CONFIG = str(Path(__file__).resolve().parent.parent / "config")


def _verdict():
    return CommitteeVerdict(bottom_line="b", whats_changing="w", switch_likelihood="将至",
                            direction="偏多", conviction="中", confidence=0.6, time_horizon="2-6周",
                            catalysts_to_watch=["CPI"], invalidation="x", positioning="多金",
                            key_disagreements=[], evidence_basis=[])


def test_pending_roundtrip(tmp_path):
    repo = CommitteeRepository(tmp_path, CONFIG)
    repo.save_pending(PendingConvocation(asset_id="GOLD", asset_name="黄金", trigger="proximity",
                      level=0.6, ratio=0.62, leader="实际利率", runner_up="央行购金", is_reversal=True, created_at="t"))
    assert [p.asset_id for p in repo.list_pending()] == ["GOLD"]
    repo.clear_pending("GOLD")
    assert repo.list_pending() == []


def test_trigger_state_roundtrip(tmp_path):
    repo = CommitteeRepository(tmp_path, CONFIG)
    repo.save_trigger_state({"GOLD": {"highest": 0.75, "vel_fired": True}})
    assert repo.load_trigger_state()["GOLD"]["highest"] == 0.75


def test_session_and_badge(tmp_path):
    repo = CommitteeRepository(tmp_path, CONFIG)
    sess = CommitteeSession(id="GOLD_t", asset_id="GOLD", asset_name="黄金", level=0.6,
                            seats=[CommitteeSeat(name="A", persona="鹰派")], rounds=1, mode="cross",
                            remarks=[SeatRemark(seat_name="A", persona="鹰派", round=1, critique="c")],
                            verdict=_verdict(), created_at="t")
    repo.save_session(sess)
    assert repo.list_sessions()[0].verdict.direction == "偏多"
    assert repo.get_badge("GOLD")["switch_likelihood"] == "将至"


def test_load_config_seats_and_skills(tmp_path):
    repo = CommitteeRepository(tmp_path, CONFIG)
    assert len(repo.skill_library()) == 12
    assert repo.default_seats() and repo.templates()
    assert "鹰派" in repo.personas()


def test_save_committee_config_roundtrip(tmp_path):
    # copy config into tmp so we don't mutate the repo's real committee.yaml
    import shutil
    cfg = tmp_path / "config"
    cfg.mkdir()
    for f in ("committee.yaml", "committee_skills.yaml"):
        shutil.copy(Path(CONFIG) / f, cfg / f)
    repo = CommitteeRepository(tmp_path, str(cfg))
    repo.save_committee_config([CommitteeSeat(name="只一个", persona="逆向", skills=["verify"])], rounds=2, mode="p2p")
    assert repo.default_rounds() == 2 and repo.default_mode() == "p2p"
    assert [s.name for s in repo.default_seats()] == ["只一个"]
