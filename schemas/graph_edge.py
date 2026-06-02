from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EdgeStatus = Literal["active", "candidate"]


class EdgeEvidenceRef(BaseModel):
    """A piece of evidence attached to an edge, with the sign-aligned contribution."""

    evidence_id: str
    created_at: str
    contribution: float = Field(ge=0.0, le=1.0)   # sign 对齐后的 strength*confidence


class GraphEdge(BaseModel):
    """A directed driver edge: src --(sign, driver)--> dst (dst is always an asset).

    sign is structural (slow, human/approval-gated); weight is dynamic
    (fast, recomputed each consolidation from decayed evidence).
    """

    id: str                                # 规范化自 f"{src}->{dst}"
    src: str                               # 因子或资产 node id
    dst: str                               # 资产 node id
    sign: Literal[1, -1]
    driver_label: str                      # 词表内
    weight: float = Field(default=0.0, ge=0.0, le=1.0)
    weight_prev: float = Field(default=0.0, ge=0.0, le=1.0)   # 上轮权重,供 velocity 触发算增量
    supporting_evidence: list[EdgeEvidenceRef] = Field(default_factory=list)
    status: EdgeStatus = "active"
    created_at: str = ""
    updated_at: str = ""
