from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TodayCard:
    asset_id: str
    name: str
    dominant_driver: str | None
    read_line: str                 # 当前状态(叙事 LLM 生成)
    strength: float
    confidence: float
    tags_regime: str | None
    is_shifting: bool
    is_contested: bool
    evidence_count: int
    # --- 立场层(确定性从图谱推导,非 LLM) ---
    lean: str = "中性"             # 偏多 | 偏空 | 中性 ← strength
    conviction: str = "低"         # 高 | 中 | 低 ← confidence
    challenger: str | None = None  # 逼近的次强驱动
    switch_kind: str | None = None # 方向反转风险 | 同向换驱动
    flip_note: str | None = None   # 切换的配置含义
    committee_badge: str | None = None  # 委员会结论徽章(如"切换将至·偏空·信心高")


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
    is_reversal: bool = False       # from/to 边异号 = 方向反转(否则同向换驱动)
    implication: str = ""
    current_lean: str = "中性"      # 资产当前偏多/偏空/中性(← strength)
    from_dir: str = ""              # 旧主导驱动 利多/利空(← from 边符号)
    to_dir: str = ""                # 新主导驱动 利多/利空(← to 边符号)


@dataclass(slots=True)
class ContestedItem:
    node_id: str
    name: str
    leader: str
    runner_up: str
    gap: float
    is_reversal: bool = False
    implication: str = ""
    current_lean: str = "中性"
    from_dir: str = ""              # 领先驱动 利多/利空
    to_dir: str = ""               # 逼近驱动(挑战者) 利多/利空


@dataclass(slots=True)
class RegimeCluster:
    regime: str
    long_names: list[str] = field(default_factory=list)
    short_names: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ShiftsView:
    """分歧预警 = 哪些资产的主导逻辑切换了 / 正在被逼近。"""

    available: bool
    shifts: list[ShiftItem] = field(default_factory=list)
    contested: list[ContestedItem] = field(default_factory=list)


@dataclass(slots=True)
class AllocationOverview:
    """跨资产配置速览:按 regime 聚类 + 方向倾向(全部从图谱确定性推导)。"""

    available: bool
    clusters: list[RegimeCluster] = field(default_factory=list)
