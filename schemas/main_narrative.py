from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


MainNarrativeStatus = Literal["active", "replaced", "archived"]


class MainNarrative(BaseModel):
    id: str
    title: str
    region: str
    theme: str
    status: MainNarrativeStatus
    version: int = Field(ge=1)
    core_claims: list[str]
    supporting_evidence: list[str]
    counter_evidence: list[str]
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    market_consensus: float = Field(ge=0.0, le=1.0)
    market_priced: float = Field(ge=0.0, le=1.0)
    fragility: list[str]
    watch_items: list[str]
    replaced_by: str | None
    effective_from: str
    updated_at: str
