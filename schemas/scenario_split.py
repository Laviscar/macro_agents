from __future__ import annotations

from pydantic import BaseModel


class ScenarioSplit(BaseModel):
    id: str
    main_narrative_id: str
    branch_narrative_id: str
    scenario_a_name: str
    scenario_a_implications: list[str]
    scenario_b_name: str
    scenario_b_implications: list[str]
    probability_split: dict[str, float]
    updated_at: str
