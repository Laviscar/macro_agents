from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TimelinePoint:
    when: str
    summary: str
    narrative_type: str  # main | branch
    direction: str       # 强化 | 削弱 | 挑战 | 中性
    strength_from: float | None
    strength_to: float | None
    confidence_from: float | None
    confidence_to: float | None
    evidence_count: int


@dataclass(slots=True)
class NarrativeTimeline:
    available: bool
    title: str
    total_commits: int                                               # commits in window (all)
    key_count: int = 0                                               # key nodes shown after filtering
    points: list[TimelinePoint] = field(default_factory=list)        # newest first (change log)
    series_labels: list[str] = field(default_factory=list)           # chronological x-axis (timestamps)
    strength_series: list[float] = field(default_factory=list)       # chronological, aligned to labels
    confidence_series: list[float] = field(default_factory=list)     # chronological, aligned to labels
