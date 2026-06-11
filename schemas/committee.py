from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CommitteeSkill(BaseModel):
    """skill 库条目(v1.7 描述性,塑造委员视角;tools 预留 v1.8 接 ToolRuntime)。"""

    id: str
    name: str
    description: str
    persona: str | None = None              # 自动组阵的天然代言人格
    tools: list[str] = Field(default_factory=list)


class CommitteeSeat(BaseModel):
    name: str
    persona: str                                   # 受控词表:鹰派/鸽派/逆向/结构派/数据派
    expertise: list[str] = Field(default_factory=list)
    llm_tier: str = "auditor_1"                     # 复用三层 + auditor_* 配置
    skills: list[str] = Field(default_factory=list) # 引用 CommitteeSkill.id


class CommitteeTemplate(BaseModel):
    id: str
    name: str
    seats: list[CommitteeSeat]
    rounds: int = 1
    mode: Literal["cross", "p2p"] = "cross"


class PendingConvocation(BaseModel):
    asset_id: str
    asset_name: str
    trigger: Literal["proximity", "velocity"]
    level: float | None = None                      # proximity 档;velocity 时 None
    velocity_delta: float | None = None             # velocity 触发时挑战驱动本轮增量
    ratio: float
    leader: str
    runner_up: str
    is_reversal: bool
    created_at: str
    status: Literal["active", "expired"] = "active"  # 同资产出现更新请求时,旧的→expired(保留)


class SeatRemark(BaseModel):
    seat_name: str
    persona: str
    round: int
    critique: str


class CommitteeVerdict(BaseModel):
    """机构投委会备忘录级结论——主席按此结构产出。"""

    bottom_line: str
    whats_changing: str
    switch_likelihood: Literal["将至", "不确定", "噪音"]
    direction: Literal["偏多", "偏空", "中性"]
    conviction: Literal["高", "中", "低"]
    confidence: float = Field(ge=0.0, le=1.0)
    time_horizon: str
    catalysts_to_watch: list[str] = Field(default_factory=list)
    invalidation: str
    positioning: str
    key_disagreements: list[str] = Field(default_factory=list)
    evidence_basis: list[str] = Field(default_factory=list)


class CommitteeSession(BaseModel):
    id: str
    asset_id: str
    asset_name: str
    level: float | None = None
    seats: list[CommitteeSeat]
    rounds: int
    mode: str
    remarks: list[SeatRemark] = Field(default_factory=list)
    verdict: CommitteeVerdict
    created_at: str = ""
