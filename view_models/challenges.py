from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AlertItem:
    challenged_claim: str
    challenge_probability: float
    branch_title: str
    key_triggers: list[str] = field(default_factory=list)
    created_at: str = ""


@dataclass(slots=True)
class ScenarioView:
    scenario_a_name: str
    scenario_a_prob: float
    scenario_b_name: str
    scenario_b_prob: float


@dataclass(slots=True)
class ChallengeItem:
    branch_id: str
    title: str
    status: str
    challenge_probability: float
    branch_strength: float
    core_claims: list[str] = field(default_factory=list)
    key_triggers: list[str] = field(default_factory=list)
    supporting_evidence_count: int = 0
    scenario: ScenarioView | None = None


@dataclass(slots=True)
class ChallengesOverview:
    available: bool
    headline: str
    alerts: list[AlertItem] = field(default_factory=list)
    challenges: list[ChallengeItem] = field(default_factory=list)  # sorted by probability desc
