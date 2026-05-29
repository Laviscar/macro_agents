import json
import pytest
from agents.analyst import AnalystAgent
from llm.base import LLMError
from llm.fake import FakeLLMClient
from schemas.resource_card import ResourceCard
from utils.clock import now_iso


def _resource_card() -> ResourceCard:
    return ResourceCard(
        id="rc_1",
        timestamp=now_iso(),
        source="test",
        url="https://example.com/x",
        title="Central bank signals slower hikes",
        one_liner="Policy tone turns dovish vs prior guidance",
        theme=["inflation", "rates"],
        importance_score=0.9,
        structural_score=0.9,
        timeliness_score=0.9,
        verifiability_score=0.9,
        analysis_readiness_score=0.9,
        route_to_analysis=True,
        route_decision="send_to_analysis",
        archive_bucket="2026_05",
    )


def test_analyze_uses_llm_output_when_client_present():
    llm_json = json.dumps({
        "mainline_relation": "supports",
        "thesis": "Dovish shift directly supports the easing mainline.",
        "confidence": 0.82,
        "signal_level": "structure",
        "reframed_question": "Does the dovish turn confirm the easing regime?",
        "evidence_for": ["tone turned dovish vs prior guidance"],
        "evidence_against": [],
        "invalidation_conditions": ["a hot CPI print reverses guidance"],
        "candidate_branch_title": None,
    })
    agent = AnalystAgent(llm_client=FakeLLMClient(responses=[llm_json]))
    card = agent.analyze(_resource_card())
    assert card.mainline_relation == "supports"
    assert card.thesis == "Dovish shift directly supports the easing mainline."
    assert card.confidence == pytest.approx(0.82)
    assert "a hot CPI print reverses guidance" in card.invalidation_conditions


def test_analyze_falls_back_to_rules_on_llm_error():
    rc = _resource_card()
    llm_agent = AnalystAgent(llm_client=FakeLLMClient(error=LLMError("boom")))
    rule_agent = AnalystAgent()
    llm_card = llm_agent.analyze(rc)
    rule_card = rule_agent.analyze(rc)
    assert llm_card.mainline_relation == rule_card.mainline_relation
    assert llm_card.thesis == rule_card.thesis


def test_analyze_falls_back_on_invalid_relation():
    bad_json = json.dumps({"mainline_relation": "not_a_real_relation", "thesis": "x", "confidence": 0.5})
    agent = AnalystAgent(llm_client=FakeLLMClient(responses=[bad_json]))
    card = agent.analyze(_resource_card())
    assert card.mainline_relation in {
        "supports", "raises_probability_of", "conflicts_with", "perturbs", "challenges", "unclear",
    }


def test_analyze_falls_back_on_non_json():
    agent = AnalystAgent(llm_client=FakeLLMClient(responses=["this is not json"]))
    card = agent.analyze(_resource_card())
    assert card.thesis


def test_extract_evidence_uses_llm_claim():
    analyze_json = json.dumps({
        "mainline_relation": "supports", "thesis": "t", "confidence": 0.8,
        "signal_level": "structure", "reframed_question": "q",
        "evidence_for": ["x"], "evidence_against": [], "invalidation_conditions": [],
        "candidate_branch_title": None,
    })
    evidence_json = json.dumps({
        "claim": "Dovish guidance lowers near-term hike odds",
        "why": "tone shift is explicit and sourced",
        "counter_evidence": ["inflation could resurge"],
        "strength": 0.77,
    })
    agent = AnalystAgent(llm_client=FakeLLMClient(responses=[analyze_json, evidence_json]))
    card = agent.analyze(_resource_card())
    evidence = agent.extract_evidence(card, context={"target_main_narrative_id": "main_default"})
    assert len(evidence) == 1
    assert evidence[0].claim == "Dovish guidance lowers near-term hike odds"
    assert evidence[0].relation_type == "supports"
    assert evidence[0].strength == pytest.approx(0.77)


def test_extract_evidence_falls_back_on_error():
    rc = _resource_card()
    analyze_json = json.dumps({
        "mainline_relation": "supports", "thesis": "t", "confidence": 0.8,
        "signal_level": "structure", "reframed_question": "q",
        "evidence_for": ["x"], "evidence_against": [], "invalidation_conditions": [],
        "candidate_branch_title": None,
    })
    agent = AnalystAgent(llm_client=FakeLLMClient(responses=[analyze_json]))
    card = agent.analyze(rc)
    agent._llm_client = FakeLLMClient(error=LLMError("evidence boom"))
    evidence = agent.extract_evidence(card, context={"target_main_narrative_id": "main_default"})
    assert len(evidence) == 1
    assert evidence[0].relation_type in {
        "supports", "raises_probability_of", "conflicts_with", "complicates", "lowers_probability_of",
    }
