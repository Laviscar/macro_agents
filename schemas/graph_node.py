from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NodeKind = Literal["asset", "factor"]
NodeLayer = Literal["anchor", "asset_class", "theme", "factor"]
NodeStatus = Literal["active", "dormant"]


class GraphNode(BaseModel):
    """A node in the narrative driver graph.

    Asset nodes have a price/ticker; factor nodes are non-tradable drivers
    (from the controlled vocabulary) that push asset prices around.
    """

    id: str
    kind: NodeKind
    name: str
    layer: NodeLayer
    ticker: str | None = None              # asset 才有
    resident: bool = False                  # 常驻(L1+L2) vs 事件驱动(L3)
    status: NodeStatus = "active"
    tags_countries: list[str] = Field(default_factory=list)
    tags_regime: str | None = None
    strength: float = Field(default=0.5, ge=0.0, le=1.0)    # 方向性信念,0.5=中性
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    dominant_driver: str | None = None      # 当前最强入边的 driver_label
    title: str = ""
    thesis: str = ""
    read_line: str = ""
    updated_at: str = ""
