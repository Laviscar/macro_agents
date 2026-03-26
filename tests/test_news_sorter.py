from agents.news_sorter import NewsSorterAgent


def test_news_sorter_routes_high_signal_to_analysis() -> None:
    agent = NewsSorterAgent()
    card = agent.process(
        {
            "title": "US CPI cools",
            "summary": "Inflation is slowing.",
            "source": "example",
            "url": "https://example.com",
            "region": ["US"],
            "theme": ["inflation"],
            "importance_score": 0.9,
            "structural_score": 0.8,
            "verifiability_score": 0.9,
        }
    )

    assert card.route_to_analysis is True
    assert card.route_decision == "send_to_analysis"
