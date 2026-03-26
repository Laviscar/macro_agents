from agents.narrative_manager import NarrativeManagerAgent
from pipelines.narrative_update import update_from_evidence
from schemas.analysis_card import AnalysisCard


def test_analysis_card_alone_cannot_trigger_narrative_update() -> None:
    narrative = NarrativeManagerAgent()
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

    state = update_from_evidence([], [analysis_card], narrative, {})

    assert "main_narrative" in state
    assert state["branches"] == []
    assert state["commits"] == []
    assert state["alerts"] == []
    assert state["scenarios"] == []
