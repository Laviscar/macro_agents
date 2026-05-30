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


def _main_narrative():
    from schemas.main_narrative import MainNarrative
    return MainNarrative(
        id="main_default", title="美国反通胀/软着陆", region="US", theme="inflation",
        status="active", version=1, core_claims=["通胀回落"], supporting_evidence=[],
        counter_evidence=[], strength=0.6, confidence=0.58, market_consensus=0.5,
        market_priced=0.5, fragility=[], watch_items=["能源价格"], replaced_by=None,
        effective_from="2026-05-30T00:00:00Z", updated_at="2026-05-30T00:00:00Z",
    )


def test_read_line_uses_llm_when_client_present():
    agent = NarrativeManagerAgent(llm_client=FakeLLMClient(responses=["反通胀延续,但能源是最大变数。"]))
    line = agent.generate_read_line(_main_narrative(), [_supports_evidence()])
    assert line == "反通胀延续,但能源是最大变数。"


def test_read_line_falls_back_to_template_on_error():
    agent = NarrativeManagerAgent(llm_client=FakeLLMClient(error=LLMError("boom")))
    line = agent.generate_read_line(_main_narrative(), [_supports_evidence()])
    assert "美国反通胀/软着陆" in line and "能源价格" in line  # rule fallback uses watch_items


def test_read_line_no_client_is_rule_based():
    agent = NarrativeManagerAgent()
    line = agent.generate_read_line(_main_narrative(), [])
    assert "美国反通胀/软着陆" in line


def _conflict_evidence(claim: str) -> Evidence:
    return Evidence(
        id="ev_conf", source_analysis_id="ac_c", source_card_ids=["rc_c"],
        claim=claim, relation_type="conflicts_with",
        target_main_narrative_id="main_default", target_branch_id=None,
        strength=0.8, confidence=0.8, why="x", counter_evidence=[],
        created_at="2026-05-30T00:00:00Z",
    )


def test_branch_title_uses_evidence_claim_when_no_candidate():
    # conflicts_with → branch created; no analysis_card → must NOT be "Branch from ..."
    agent = NarrativeManagerAgent()
    state = agent.update([_conflict_evidence("美国能源主导地位面临地缘反噬")], None, {})
    assert len(state["branches"]) == 1
    title = state["branches"][0].title
    assert not title.startswith("Branch from")
    assert "美国能源主导地位面临地缘反噬" in title
