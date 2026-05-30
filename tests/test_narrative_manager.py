from agents.narrative_manager import NarrativeManagerAgent
from schemas.analysis_card import AnalysisCard
from schemas.evidence import Evidence


def test_narrative_manager_updates_with_evidence() -> None:
    agent = NarrativeManagerAgent()
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

    evidence = Evidence(
        id="ev_001",
        source_analysis_id="ac_001",
        source_card_ids=["rc_001"],
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

    state = agent.update([evidence], analysis_card, {})

    assert "main_narrative" in state
    assert state["branches"] == []
    assert state["alerts"] == []
    assert state["scenarios"] == []
    assert len(state["commits"]) == 1
    assert state["commits"][0].source_evidence_ids == ["ev_001"]
    assert state["main_narrative"].supporting_evidence == ["ev_001"]
    assert state["main_narrative"].strength > 0.5
    assert state["commits"][0].narrative_type == "main"


def test_narrative_manager_complicates_updates_fragility_and_watch_items() -> None:
    agent = NarrativeManagerAgent()
    evidence = Evidence(
        id="ev_002",
        source_analysis_id="ac_002",
        source_card_ids=["rc_002"],
        claim="就业与通胀信号出现分化",
        relation_type="complicates",
        target_main_narrative_id="main_default",
        target_branch_id=None,
        strength=0.6,
        confidence=0.65,
        why="就业偏强但通胀继续回落",
        counter_evidence=[],
        created_at="2026-03-25T00:00:00Z",
    )

    state = agent.update([evidence], None, {})

    assert state["main_narrative"].fragility == ["就业与通胀信号出现分化"]
    assert state["main_narrative"].watch_items == ["就业与通胀信号出现分化"]
    assert state["main_narrative"].supporting_evidence == []
    assert state["main_narrative"].counter_evidence == []
    assert state["branches"] == []
    assert state["alerts"] == []
    assert state["scenarios"] == []
    assert state["commits"][0].narrative_type == "main"


def test_narrative_manager_conflicts_with_creates_branch_path() -> None:
    agent = NarrativeManagerAgent()
    evidence = Evidence(
        id="ev_003",
        source_analysis_id="ac_003",
        source_card_ids=["rc_003"],
        claim="核心通胀重新走高",
        relation_type="conflicts_with",
        target_main_narrative_id="main_default",
        target_branch_id=None,
        strength=0.8,
        confidence=0.75,
        why="核心服务通胀高于预期",
        counter_evidence=[],
        created_at="2026-03-25T00:00:00Z",
    )

    state = agent.update([evidence], None, {})

    assert state["main_narrative"].supporting_evidence == []
    assert state["main_narrative"].counter_evidence == ["ev_003"]
    assert len(state["branches"]) == 1
    assert state["branches"][0].supporting_evidence == ["ev_003"]
    assert state["branches"][0].counter_evidence == []
    assert state["branches"][0].branch_strength > 0.4
    assert state["branches"][0].challenge_probability > 0.5
    assert state["commits"][0].narrative_type == "branch"


def test_narrative_manager_lowers_probability_of_creates_branch_path() -> None:
    agent = NarrativeManagerAgent()
    evidence = Evidence(
        id="ev_004",
        source_analysis_id="ac_004",
        source_card_ids=["rc_004"],
        claim="增长韧性不足的概率上升",
        relation_type="lowers_probability_of",
        target_main_narrative_id="main_default",
        target_branch_id=None,
        strength=0.7,
        confidence=0.65,
        why="消费与就业同步转弱",
        counter_evidence=[],
        created_at="2026-03-25T00:00:00Z",
    )

    state = agent.update([evidence], None, {})

    assert state["main_narrative"].supporting_evidence == []
    assert state["main_narrative"].counter_evidence == ["ev_004"]
    assert len(state["branches"]) == 1
    assert state["branches"][0].supporting_evidence == ["ev_004"]
    assert state["branches"][0].counter_evidence == []
    assert state["branches"][0].branch_strength > 0.3
    assert state["branches"][0].challenge_probability > 0.5
    assert state["commits"][0].narrative_type == "branch"


def test_commit_summary_uses_evidence_claim_not_template() -> None:
    agent = NarrativeManagerAgent()
    evidence = Evidence(
        id="ev_claim",
        source_analysis_id="ac_x",
        source_card_ids=["rc_x"],
        claim="美国燃料出口创纪录,强化能源主导叙事",
        relation_type="supports",
        target_main_narrative_id="main_default",
        target_branch_id=None,
        strength=0.8,
        confidence=0.8,
        why="出口数据",
        counter_evidence=[],
        created_at="2026-05-30T00:00:00Z",
    )
    state = agent.update([evidence], None, {})
    summary = state["commits"][0].summary
    assert "美国燃料出口创纪录,强化能源主导叙事" in summary  # real claim, not "因 supports evidence"
    assert "强化主线" in summary


def test_commit_summary_falls_back_to_template_when_claim_empty() -> None:
    agent = NarrativeManagerAgent()
    evidence = Evidence(
        id="ev_blank",
        source_analysis_id="ac_y",
        source_card_ids=["rc_y"],
        claim="",  # no claim text → template fallback
        relation_type="supports",
        target_main_narrative_id="main_default",
        target_branch_id=None,
        strength=0.6,
        confidence=0.6,
        why="x",
        counter_evidence=[],
        created_at="2026-05-30T00:00:00Z",
    )
    state = agent.update([evidence], None, {})
    assert "因 supports evidence 被强化" in state["commits"][0].summary
