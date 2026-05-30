import json
import logging
import pytest
from agents.triage import TriageAgent
from llm.base import LLMError
from llm.fake import FakeLLMClient
from schemas.resource_card import ResourceCard
from utils.clock import now_iso


def _card(title="US CPI cools more than expected") -> ResourceCard:
    return ResourceCard(
        id="rc_1", timestamp=now_iso(), source="test", url="https://x", title=title,
        one_liner="inflation slowed again", region=["Global"], theme=["inflation"],
        card_type="news", tags=[], importance_score=0.5, structural_score=0.5,
        timeliness_score=0.5, verifiability_score=0.5, analysis_readiness_score=0.5,
        route_to_analysis=False, route_decision="watchlist", archive_bucket="2026_05",
    )


def test_important_true_from_primary():
    primary = FakeLLMClient(responses=[json.dumps({"important": True, "reason": "macro"})])
    agent = TriageAgent(primary_client=primary)
    assert agent.is_important(_card()) is True


def test_unimportant_false_from_primary():
    primary = FakeLLMClient(responses=[json.dumps({"important": False, "reason": "noise"})])
    agent = TriageAgent(primary_client=primary)
    assert agent.is_important(_card()) is False


def test_degrades_to_fallback_and_warns(caplog):
    primary = FakeLLMClient(error=LLMError("cheap down"))
    fallback = FakeLLMClient(responses=[json.dumps({"important": True, "reason": "x"})])
    agent = TriageAgent(primary_client=primary, fallback_client=fallback)
    with caplog.at_level(logging.WARNING):
        result = agent.is_important(_card())
    assert result is True
    assert agent.degraded_count == 1
    assert any("triage" in r.message.lower() or "degrad" in r.message.lower() for r in caplog.records)


def test_fails_open_when_both_fail():
    primary = FakeLLMClient(error=LLMError("down"))
    fallback = FakeLLMClient(error=LLMError("also down"))
    agent = TriageAgent(primary_client=primary, fallback_client=fallback)
    assert agent.is_important(_card()) is True


def test_fails_open_when_no_client():
    agent = TriageAgent(primary_client=None)
    assert agent.is_important(_card()) is True
