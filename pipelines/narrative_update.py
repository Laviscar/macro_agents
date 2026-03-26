from __future__ import annotations

from agents.narrative_manager import NarrativeManagerAgent
from schemas.analysis_card import AnalysisCard
from schemas.evidence import Evidence


def update_from_evidence(
    evidence_list: list[Evidence],
    analysis_cards: list[AnalysisCard],
    agent: NarrativeManagerAgent,
    state: dict | None = None,
) -> dict:
    """
    叙事更新必须以 Evidence 为唯一触发入口。

    AnalysisCard 只作为已有 Evidence 的辅助上下文，不允许单独驱动更新。
    """
    current_state = agent.update([], None, state)
    for analysis_card in analysis_cards:
        related_evidence = [item for item in evidence_list if item.source_analysis_id == analysis_card.id]
        if not related_evidence:
            continue
        current_state = agent.update(related_evidence, analysis_card, current_state)
    return current_state
