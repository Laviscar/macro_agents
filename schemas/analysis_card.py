from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SignalLevel = Literal["fact", "product", "structure", "institution", "theme_candidate"]
MainlineRelation = Literal[
    "supports",
    "raises_probability_of",
    "conflicts_with",
    "perturbs",
    "challenges",
    "unclear",
]


class AnalysisCard(BaseModel):
    id: str
    event_id: str
    source_card_ids: list[str]
    reframed_question: str
    signal_level: SignalLevel
    thesis: str
    evidence_for: list[str]
    evidence_against: list[str]
    macro_variables: list[str]
    asset_mapping: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    mainline_relation: MainlineRelation
    candidate_branch_title: str | None
    invalidation_conditions: list[str]
    created_at: str
