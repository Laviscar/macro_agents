from __future__ import annotations

from agents.analyst import AnalystAgent
from schemas.analysis_card import AnalysisCard
from schemas.evidence import Evidence


def extract_evidence_from_analysis(
    analysis_cards: list[AnalysisCard],
    agent: AnalystAgent,
    context: dict | None = None,
) -> list[Evidence]:
    evidence_list: list[Evidence] = []
    for analysis_card in analysis_cards:
        evidence_list.extend(agent.extract_evidence(analysis_card, context=context or {}))
    return evidence_list
