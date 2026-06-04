from __future__ import annotations

from pydantic import BaseModel


class FredReading(BaseModel):
    """一条 FRED 硬数据读数(数值真相层,不经 LLM)。"""

    series_id: str
    label: str
    unit: str
    node_id: str | None = None     # 映射到图节点;None = 通用宏观读数
    value: float
    date: str                      # 最新观测日期
    prev: float | None = None
    change: float | None = None    # value - prev
    fetched_at: str = ""
