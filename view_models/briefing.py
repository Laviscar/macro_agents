from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BriefingChange:
    when: str
    summary: str
    direction: str  # 强化 | 削弱 | 挑战 | 中性


@dataclass(slots=True)
class BriefingBranch:
    title: str
    challenge_probability: float
    key_triggers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BriefingOverview:
    available: bool
    title: str
    status: str
    read_line: str
    strength: float
    confidence: float
    strength_delta: float | None
    confidence_delta: float | None
    strength_series: list[float] = field(default_factory=list)
    recent_changes: list[BriefingChange] = field(default_factory=list)
    top_branches: list[BriefingBranch] = field(default_factory=list)
    updated_at: str = ""
