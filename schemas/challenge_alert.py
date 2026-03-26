from __future__ import annotations

from pydantic import BaseModel, Field


class ChallengeAlert(BaseModel):
    id: str
    main_narrative_id: str
    branch_narrative_id: str
    challenged_claim: str
    challenge_probability: float = Field(ge=0.0, le=1.0)
    key_triggers: list[str]
    sensitive_assets: list[str]
    scenario_a_main_holds: list[str]
    scenario_b_branch_takes_over: list[str]
    created_at: str
