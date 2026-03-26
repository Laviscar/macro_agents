from __future__ import annotations

from agents.analyst import AnalystAgent
from schemas.analysis_card import AnalysisCard
from schemas.resource_card import ResourceCard


def analyze_resource_cards(
    resource_cards: list[ResourceCard],
    agent: AnalystAgent,
    context: dict | None = None,
) -> list[AnalysisCard]:
    selected_cards = [card for card in resource_cards if card.route_to_analysis]
    return [agent.analyze(card, context=context or {}) for card in selected_cards]
