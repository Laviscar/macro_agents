import json
import pytest
from agents.narrative_manager import NarrativeManagerAgent
from llm.base import LLMError
from llm.fake import FakeLLMClient
from schemas.evidence import Evidence


def _supports_evidence() -> Evidence:
    return Evidence(
        id="ev_llm_1",
        source_analysis_id="ac_1",
        source_card_ids=["rc_1"],
        claim="通胀回落正在强化主线",
        relation_type="supports",
        target_main_narrative_id="main_default",
        target_branch_id=None,
        strength=0.7,
        confidence=0.7,
        why="CPI 低于预期",
        counter_evidence=[],
        created_at="2026-03-25T00:00:00Z",
    )


def test_llm_can_force_open_branch_against_rule_default():
    llm_json = json.dumps({"challenge_probability": 0.8, "open_branch": True, "reason": "hidden fragility"})
    agent = NarrativeManagerAgent(llm_client=FakeLLMClient(responses=[llm_json]))
    state = agent.update([_supports_evidence()], None, {})
    assert len(state["branches"]) == 1
    assert len(state["alerts"]) == 1


def test_falls_back_to_rules_on_llm_error():
    llm_agent = NarrativeManagerAgent(llm_client=FakeLLMClient(error=LLMError("boom")))
    rule_agent = NarrativeManagerAgent()
    llm_state = llm_agent.update([_supports_evidence()], None, {})
    rule_state = rule_agent.update([_supports_evidence()], None, {})
    assert len(llm_state["branches"]) == len(rule_state["branches"]) == 0


def test_falls_back_on_invalid_open_branch_type():
    bad = json.dumps({"challenge_probability": 0.9, "open_branch": "yes"})
    agent = NarrativeManagerAgent(llm_client=FakeLLMClient(responses=[bad]))
    state = agent.update([_supports_evidence()], None, {})
    assert len(state["branches"]) == 0


def test_falls_back_on_non_json():
    agent = NarrativeManagerAgent(llm_client=FakeLLMClient(responses=["not json"]))
    state = agent.update([_supports_evidence()], None, {})
    assert len(state["branches"]) == 0


def test_no_client_is_pure_rule_path():
    agent = NarrativeManagerAgent()
    state = agent.update([_supports_evidence()], None, {})
    assert len(state["branches"]) == 0
