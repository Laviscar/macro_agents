from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


RelationType = Literal[
    "supports",
    "conflicts_with",
    "complicates",
    "raises_probability_of",
    "lowers_probability_of",
]


class Evidence(BaseModel):
    id: str
    source_analysis_id: str
    source_card_ids: list[str]
    claim: str
    relation_type: RelationType
    target_main_narrative_id: str | None = None
    target_branch_id: str | None = None
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    why: str
    counter_evidence: list[str] = Field(default_factory=list)
    created_at: str

    @model_validator(mode="after")
    def validate_target_presence(self) -> "Evidence":
        if not self.target_main_narrative_id and not self.target_branch_id:
            raise ValueError("Evidence must target at least one narrative object.")
        return self
