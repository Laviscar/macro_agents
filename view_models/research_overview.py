from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MainNarrativeCard:
    narrative_id: str
    title: str
    status: str
    headline: str
    summary: str
    strength: float
    confidence: float
    reinforcing_factors: list[str]
    fragility_factors: list[str]
    challenge_count: int
    watch_items: list[str]
    updated_at: str


@dataclass(slots=True)
class ChallengeBranchCard:
    branch_id: str
    title: str
    status: str
    headline: str
    challenge_probability: float
    supporting_factors: list[str]
    key_triggers: list[str]
    parent_main_narrative_id: str
    updated_at: str


@dataclass(slots=True)
class ResearchOverview:
    main_cards: list[MainNarrativeCard]
    challenge_branches: list[ChallengeBranchCard]
    global_headline: str
    global_summary: str
    updated_at: str
