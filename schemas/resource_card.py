from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RouteDecision = Literal["archive_only", "watchlist", "send_to_analysis", "discard_noise"]
CardType = Literal["news", "research", "data_release", "policy_text", "manual_note"]


class ResourceCard(BaseModel):
    id: str
    timestamp: str
    source: str
    url: str
    title: str
    one_liner: str
    region: list[str] = Field(default_factory=list)
    theme: list[str] = Field(default_factory=list)
    card_type: CardType = "news"
    tags: list[str] = Field(default_factory=list)
    importance_score: float = Field(ge=0.0, le=1.0)
    structural_score: float = Field(ge=0.0, le=1.0)
    timeliness_score: float = Field(ge=0.0, le=1.0)
    verifiability_score: float = Field(ge=0.0, le=1.0)
    analysis_readiness_score: float = Field(ge=0.0, le=1.0)
    route_to_analysis: bool
    route_decision: RouteDecision
    archive_bucket: str
