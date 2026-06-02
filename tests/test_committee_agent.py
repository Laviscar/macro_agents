import json

from agents.committee import ChairSynthesizer, NarrativeCommittee, SeatRunner
from llm.base import LLMError
from llm.fake import FakeLLMClient
from schemas.committee import CommitteeSeat, PendingConvocation

SKILL_DESC = {"rates_curve": "久期/曲线视角", "verify": "追一手来源、不编数"}

_MEMO = json.dumps({
    "bottom_line": "金价短期偏多", "whats_changing": "驱动从实际利率转央行购金", "switch_likelihood": "将至",
    "direction": "偏多", "conviction": "中", "confidence": 0.7, "time_horizon": "2-6周",
    "catalysts_to_watch": ["FOMC", "CPI"], "invalidation": "实际利率大幅回升", "positioning": "多黄金",
    "key_disagreements": ["逆向派认为已price-in"], "evidence_basis": ["央行连续增持"]})


# --- SeatRunner ---
def test_seat_prompt_includes_persona_and_skill():
    llm = FakeLLMClient(responses=["利率角度看,这是噪音"])
    seat = CommitteeSeat(name="鹰派-利率", persona="鹰派", expertise=["利率"], skills=["rates_curve"])
    remark = SeatRunner(seat, llm, SKILL_DESC).critique(context="GOLD: 实际利率 vs 央行购金", peers=None, round_no=1)
    sent = llm.calls[0][0].content + llm.calls[0][1].content
    assert "鹰派" in sent and ("久期" in sent or "rates_curve" in sent)
    assert remark.critique == "利率角度看,这是噪音" and remark.persona == "鹰派"


def test_failed_seat_returns_none():
    seat = CommitteeSeat(name="x", persona="鸽派")
    runner = SeatRunner(seat, FakeLLMClient(error=LLMError("down")), {})
    assert runner.critique(context="c", peers=None, round_no=1) is None


# --- ChairSynthesizer ---
def test_chair_produces_memo_verdict():
    v = ChairSynthesizer(FakeLLMClient(responses=[_MEMO])).synthesize(context="ctx", remarks_text="...")
    assert v.switch_likelihood == "将至" and v.conviction == "中"
    assert v.catalysts_to_watch == ["FOMC", "CPI"] and v.invalidation.startswith("实际利率")


def test_chair_failure_returns_uncertain_stub():
    v = ChairSynthesizer(FakeLLMClient(error=LLMError("x"))).synthesize(context="c", remarks_text="r")
    assert v.switch_likelihood == "不确定" and v.confidence == 0.0


# --- convene ---
def test_convene_runs_seats_then_chair():
    seats = [(CommitteeSeat(name="鹰", persona="鹰派", skills=["rates_curve"]), FakeLLMClient(responses=["r1"])),
             (CommitteeSeat(name="鸽", persona="鸽派", skills=["verify"]), FakeLLMClient(responses=["r2"]))]
    chair = FakeLLMClient(responses=[_MEMO])
    pend = PendingConvocation(asset_id="GOLD", asset_name="黄金", trigger="proximity", level=0.75,
                              ratio=0.8, leader="实际利率", runner_up="央行购金", is_reversal=True, created_at="t")
    cm = NarrativeCommittee(seats=seats, chair_client=chair, rounds=1, mode="cross", skill_desc=SKILL_DESC)
    session = cm.convene(pending=pend, context="GOLD 当前偏多;实际利率 vs 央行购金")
    assert session.asset_id == "GOLD" and len(session.remarks) == 2
    assert session.verdict.switch_likelihood == "将至" and session.verdict.key_disagreements == ["逆向派认为已price-in"]


def test_seat_with_no_client_skipped():
    from schemas.committee import CommitteeSeat
    runner = SeatRunner(CommitteeSeat(name="x", persona="鹰派"), client=None, skill_desc={})
    assert runner.critique(context="c", peers=None, round_no=1) is None


def test_chair_with_no_client_returns_stub():
    v = ChairSynthesizer(client=None).synthesize(context="c", remarks_text="r")
    assert v.switch_likelihood == "不确定" and v.confidence == 0.0
