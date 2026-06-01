from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TodayCard:
    asset_id: str
    name: str
    dominant_driver: str | None
    read_line: str
    strength: float
    confidence: float
    tags_regime: str | None
    is_shifting: bool
    is_contested: bool
    evidence_count: int


@dataclass(slots=True)
class TodayView:
    """今日叙事 = 从所有资产里排出最值得看的几条(P1.1 的正解)。"""

    available: bool
    cards: list[TodayCard] = field(default_factory=list)
    total_assets: int = 0


@dataclass(slots=True)
class ShiftItem:
    node_id: str
    name: str
    from_driver: str
    to_driver: str
    at: str


@dataclass(slots=True)
class ContestedItem:
    node_id: str
    name: str
    leader: str
    runner_up: str
    gap: float


@dataclass(slots=True)
class ShiftsView:
    """分歧预警 = 哪些资产的主导逻辑切换了 / 正在被逼近。"""

    available: bool
    shifts: list[ShiftItem] = field(default_factory=list)
    contested: list[ContestedItem] = field(default_factory=list)
