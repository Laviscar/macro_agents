import json
import logging
import pytest
from agents.audit import AuditPanel
from llm.base import LLMError
from llm.fake import FakeLLMClient

_J = {"challenge_probability": 0.7, "open_branch": True}


def _critique(text):
    return json.dumps({"critique": text, "suggested_probability": None, "suggested_open_branch": None})


class RecRejudge:
    """Records each rejudge call; returns queued outputs (or echoes the input)."""
    def __init__(self, outputs=None):
        self.calls = []
        self._outputs = list(outputs or [])

    def __call__(self, judgment, critiques, context):
        self.calls.append({"judgment": dict(judgment), "critiques": list(critiques)})
        return self._outputs.pop(0) if self._outputs else dict(judgment)


def test_no_seats_returns_judgment_unchanged():
    rj = RecRejudge()
    panel = AuditPanel(seat_clients=[], rounds=2)
    assert panel.run(_J, "ctx", rj) == _J
    assert rj.calls == []  # rejudge never called
    assert panel.seat_count == 0 and panel.mode == "cross"


def test_cross_calls_rejudge_once_with_final_round_critiques():
    s1 = FakeLLMClient(responses=[_critique("c1r1"), _critique("c1r2")])
    s2 = FakeLLMClient(responses=[_critique("c2r1"), _critique("c2r2")])
    rj = RecRejudge(outputs=[{"challenge_probability": 0.9, "open_branch": True}])
    out = AuditPanel(seat_clients=[s1, s2], rounds=2, mode="cross").run(_J, "ctx", rj)
    assert out == {"challenge_probability": 0.9, "open_branch": True}
    assert len(rj.calls) == 1                                   # concluded once
    assert rj.calls[0]["critiques"] == ["c1r2", "c2r2"]         # final-round critiques
    # round-2 critique prompt for s1 saw round-1 peer critiques
    assert "c2r1" in s1.calls[1][-1].content or "c1r1" in s1.calls[1][-1].content


def test_p2p_calls_rejudge_each_round_no_peer_visibility():
    seat = FakeLLMClient(responses=[_critique("r1"), _critique("r2")])
    rj = RecRejudge(outputs=[{"challenge_probability": 0.5, "open_branch": False},
                             {"challenge_probability": 0.85, "open_branch": True}])
    out = AuditPanel(seat_clients=[seat], rounds=2, mode="p2p").run(_J, "ctx", rj)
    assert out == {"challenge_probability": 0.85, "open_branch": True}
    assert len(rj.calls) == 2                                   # manager revised every round
    # round 2 critiqued the round-1 revised judgment (cp 0.5), not the original 0.7
    assert rj.calls[1]["judgment"]["challenge_probability"] == 0.5
    # p2p: seats never get a peers block
    assert "Other auditors said" not in seat.calls[1][-1].content


def test_failing_seat_skipped_with_warning(caplog):
    good = FakeLLMClient(responses=[_critique("ok")])
    bad = FakeLLMClient(error=LLMError("down"))
    rj = RecRejudge(outputs=[{"challenge_probability": 0.6, "open_branch": False}])
    with caplog.at_level(logging.WARNING):
        AuditPanel(seat_clients=[good, bad], rounds=1).run(_J, "ctx", rj)
    assert rj.calls[0]["critiques"] == ["ok"]                   # only the good seat
    assert any("audit" in r.message.lower() for r in caplog.records)


def test_all_seats_fail_returns_judgment_no_rejudge():
    rj = RecRejudge()
    out = AuditPanel(seat_clients=[FakeLLMClient(error=LLMError("x"))], rounds=1).run(_J, "ctx", rj)
    assert out == _J and rj.calls == []


def test_invalid_mode_defaults_to_cross():
    assert AuditPanel(seat_clients=[], mode="bogus").mode == "cross"
