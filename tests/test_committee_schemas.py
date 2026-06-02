from schemas.committee import (
    CommitteeSeat,
    CommitteeSession,
    CommitteeVerdict,
    PendingConvocation,
    SeatRemark,
)


def _verdict(**kw):
    base = dict(bottom_line="b", whats_changing="w", switch_likelihood="将至", direction="偏多",
                conviction="中", confidence=0.6, time_horizon="2-6周", catalysts_to_watch=["CPI"],
                invalidation="实际利率回升", positioning="多黄金", key_disagreements=["d"], evidence_basis=["央行增持"])
    base.update(kw)
    return CommitteeVerdict(**base)


def test_seat_defaults():
    s = CommitteeSeat(name="A", persona="鹰派")
    assert s.llm_tier == "auditor_1" and s.skills == [] and s.expertise == []


def test_pending_velocity_has_no_level():
    p = PendingConvocation(asset_id="GOLD", asset_name="黄金", trigger="velocity",
                           velocity_delta=0.2, ratio=0.5, leader="实际利率", runner_up="央行购金",
                           is_reversal=True, created_at="t")
    assert p.level is None and p.trigger == "velocity"


def test_verdict_is_memo_grade():
    v = _verdict()
    assert v.switch_likelihood == "将至" and v.evidence_basis == ["央行增持"]


def test_session_roundtrips():
    seat = CommitteeSeat(name="A", persona="鹰派")
    sess = CommitteeSession(id="GOLD_t", asset_id="GOLD", asset_name="黄金", level=0.6, seats=[seat],
                            rounds=1, mode="cross",
                            remarks=[SeatRemark(seat_name="A", persona="鹰派", round=1, critique="c")],
                            verdict=_verdict(direction="中性", switch_likelihood="噪音"))
    again = CommitteeSession.model_validate_json(sess.model_dump_json())
    assert again.verdict.direction == "中性" and again.remarks[0].critique == "c"
