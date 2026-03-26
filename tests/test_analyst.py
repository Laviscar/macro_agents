from agents.analyst import AnalystAgent
from schemas.resource_card import ResourceCard


def test_analyst_generates_analysis_card() -> None:
    agent = AnalystAgent()
    card = ResourceCard(
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

    analysis = agent.analyze(card)
    assert analysis.event_id == "rc_001"
    assert analysis.thesis != ""
    assert analysis.mainline_relation == "supports"
