import json
import logging
import pytest
from agents.audit import AuditPanel
from llm.base import LLMError
from llm.fake import FakeLLMClient

_J = {"challenge_probability": 0.7, "open_branch": True}


def _critique(text):
    return json.dumps({"critique": text, "suggested_probability": None, "suggested_open_branch": None})


def test_no_seats_returns_empty():
    assert AuditPanel(seat_clients=[], rounds=1).deliberate(_J, "ctx") == []
    assert AuditPanel(seat_clients=[], rounds=1).seat_count == 0


def test_one_seat_one_round_returns_one_critique():
    seat = FakeLLMClient(responses=[_critique("overconfident")])
    out = AuditPanel(seat_clients=[seat], rounds=1).deliberate(_J, "ctx")
    assert out == ["overconfident"]


def test_two_rounds_second_sees_first_round_peer_critiques():
    s1 = FakeLLMClient(responses=[_critique("c1r1"), _critique("c1r2")])
    s2 = FakeLLMClient(responses=[_critique("c2r1"), _critique("c2r2")])
    out = AuditPanel(seat_clients=[s1, s2], rounds=2).deliberate(_J, "ctx")
    assert out == ["c1r2", "c2r2"]
    round2_user = s1.calls[1][-1].content
    assert "c2r1" in round2_user or "c1r1" in round2_user


def test_failing_seat_is_skipped_with_warning(caplog):
    good = FakeLLMClient(responses=[_critique("ok")])
    bad = FakeLLMClient(error=LLMError("down"))
    with caplog.at_level(logging.WARNING):
        out = AuditPanel(seat_clients=[good, bad], rounds=1).deliberate(_J, "ctx")
    assert out == ["ok"]
    assert any("audit" in r.message.lower() for r in caplog.records)


def test_all_seats_fail_returns_empty():
    out = AuditPanel(seat_clients=[FakeLLMClient(error=LLMError("x"))], rounds=1).deliberate(_J, "ctx")
    assert out == []
