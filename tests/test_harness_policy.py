import pytest
from harness.policy import PolicyDecision, PolicyEngine, PolicyRecord, RiskLevel


def test_low_risk_is_allowed():
    engine = PolicyEngine()
    decision, reason = engine.evaluate("read_db", RiskLevel.LOW)
    assert decision == PolicyDecision.ALLOW
    assert isinstance(reason, str)


def test_medium_risk_is_allowed():
    engine = PolicyEngine()
    decision, reason = engine.evaluate("write_local", RiskLevel.MEDIUM)
    assert decision == PolicyDecision.ALLOW


def test_high_risk_requires_approval():
    engine = PolicyEngine()
    decision, reason = engine.evaluate("call_llm", RiskLevel.HIGH)
    assert decision == PolicyDecision.ASK_FOR_APPROVAL


def test_critical_risk_is_denied():
    engine = PolicyEngine()
    decision, reason = engine.evaluate("send_webhook", RiskLevel.CRITICAL)
    assert decision == PolicyDecision.DENY


def test_record_returns_policy_record():
    engine = PolicyEngine()
    record = engine.record("sort_tool", RiskLevel.LOW)
    assert isinstance(record, PolicyRecord)
    assert record.tool_name == "sort_tool"
    assert record.risk_level == RiskLevel.LOW
    assert record.decision == PolicyDecision.ALLOW
    assert len(record.reason) > 0
    assert len(record.created_at) > 0


def test_risk_level_string_values():
    assert RiskLevel.LOW == "low"
    assert RiskLevel.MEDIUM == "medium"
    assert RiskLevel.HIGH == "high"
    assert RiskLevel.CRITICAL == "critical"


def test_policy_decision_string_values():
    assert PolicyDecision.ALLOW == "allow"
    assert PolicyDecision.DENY == "deny"
    assert PolicyDecision.ASK_FOR_APPROVAL == "ask_for_approval"
