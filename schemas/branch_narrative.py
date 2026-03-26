from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


BranchStatus = Literal["seed", "watching", "strengthening", "challenger", "promoted", "faded"]


class BranchNarrative(BaseModel):
    id: str
    parent_main_narrative_id: str
    title: str
    region: str
    theme: str
    status: BranchStatus
    core_claims: list[str]
    supporting_evidence: list[str]
    counter_evidence: list[str]
    branch_strength: float = Field(ge=0.0, le=1.0)
    challenge_probability: float = Field(ge=0.0, le=1.0)
    market_priced: float = Field(ge=0.0, le=1.0)
    fragility: list[str]
    key_triggers: list[str]
    created_at: str
    updated_at: str
