from agents.analyst import AnalystAgent
from schemas.analysis_card import AnalysisCard


def test_extract_evidence() -> None:
    analyst = AnalystAgent()
    analysis_card = AnalysisCard(
        id="ac_001",
        event_id="rc_001",
        source_card_ids=["rc_001"],
        reframed_question="这是否改变主线？",
        signal_level="structure",
        thesis="通胀回落可能强化软着陆主线",
        evidence_for=["CPI 低于预期"],
        evidence_against=[],
        macro_variables=["inflation"],
        asset_mapping=[],
        confidence=0.7,
        mainline_relation="supports",
        candidate_branch_title=None,
        invalidation_conditions=[],
        created_at="2026-03-25T00:00:00Z",
    )

    evidence_list = analyst.extract_evidence(
        analysis_card,
        context={"target_main_narrative_id": "main_us_001"},
    )

    assert len(evidence_list) == 1
    assert evidence_list[0].target_main_narrative_id == "main_us_001"
    assert evidence_list[0].claim != analysis_card.thesis
    assert len(evidence_list[0].claim) < len(analysis_card.thesis)
    assert evidence_list[0].relation_type == "supports"
    assert evidence_list[0].counter_evidence == []
    assert analysis_card.thesis not in evidence_list[0].why
    assert analysis_card.reframed_question not in evidence_list[0].why
    assert "关键依据" not in evidence_list[0].why
