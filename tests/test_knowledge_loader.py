from agents.analyst import AnalystAgent
from agents.narrative_manager import NarrativeManagerAgent
from schemas.analysis_card import AnalysisCard
from schemas.evidence import Evidence
from schemas.resource_card import ResourceCard
from utils.knowledge_loader import KnowledgeLoader


def test_knowledge_loader_and_agent_context() -> None:
    loader = KnowledgeLoader("knowledge/registry.yaml")

    analyst_context = loader.load_context("analyst", tasks=["analyze_event", "extract_evidence"])
    narrative_context = loader.load_context("narrative_manager", tasks=["record_commit"])

    analyst = AnalystAgent(knowledge_context=analyst_context)
    narrative = NarrativeManagerAgent(knowledge_context=narrative_context)

    resource_card = ResourceCard(
        id="rc_001",
        timestamp="2026-03-25T00:00:00Z",
        source="example",
        url="https://example.com",
        title="US CPI cools",
        one_liner="Inflation is slowing.",
        region=["US"],
        theme=["inflation"],
        card_type="news",
        tags=["cpi"],
        importance_score=0.9,
        structural_score=0.8,
        timeliness_score=0.8,
        verifiability_score=0.9,
        analysis_readiness_score=0.86,
        route_to_analysis=True,
        route_decision="send_to_analysis",
        archive_bucket="2026_03",
    )
    analysis = analyst.analyze(resource_card)
    analyst.extract_evidence(analysis, context={"target_main_narrative_id": "main_default"})

    evidence = Evidence(
        id="ev_001",
        source_analysis_id=analysis.id,
        source_card_ids=["rc_001"],
        claim="US CPI cooled",
        relation_type="supports",
        target_main_narrative_id="main_default",
        target_branch_id=None,
        strength=0.6,
        confidence=0.6,
        why="Inflation is slowing",
        counter_evidence=[],
        created_at="2026-03-25T00:00:00Z",
    )
    analysis_card = AnalysisCard(
        id=analysis.id,
        event_id="rc_001",
        source_card_ids=["rc_001"],
        reframed_question="这是否改变主线？",
        signal_level="structure",
        thesis=analysis.thesis,
        evidence_for=["Inflation is slowing."],
        evidence_against=[],
        macro_variables=["inflation"],
        asset_mapping=[],
        confidence=0.6,
        mainline_relation=analysis.mainline_relation,
        candidate_branch_title=None,
        invalidation_conditions=[],
        created_at="2026-03-25T00:00:00Z",
    )
    narrative.update([evidence], analysis_card, {})

    assert [doc["id"] for doc in analyst.last_knowledge_docs["analyze_event"]] == [
        "signal_levels",
        "analyst_master",
        "confidence_rubric",
    ]
    assert [doc["id"] for doc in analyst.last_knowledge_docs["extract_evidence"]] == [
        "signal_levels",
        "analyst_master",
        "confidence_rubric",
        "evidence_extraction",
    ]
    assert [doc["id"] for doc in narrative.last_knowledge_docs["record_commit"]] == [
        "signal_levels",
        "narrative_master",
        "confidence_rubric",
        "commit_logging",
    ]
