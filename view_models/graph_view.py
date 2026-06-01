from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class GraphViewNode:
    id: str
    name: str
    kind: str            # asset | factor
    layer: str           # anchor | asset_class | theme | factor
    status: str          # active | dormant
    strength: float
    confidence: float
    dominant_driver: str | None
    tags_regime: str | None
    tags_countries: list[str]
    title: str
    read_line: str
    is_shifting: bool = False    # appeared in a recent driver shift


@dataclass(slots=True)
class GraphViewEdge:
    src: str
    dst: str
    sign: int
    driver_label: str
    weight: float
    is_dominant: bool = False    # currently the dst's dominant driver


@dataclass(slots=True)
class GraphView:
    """Renderer-agnostic graph snapshot — the single JSON contract every UI consumes."""

    nodes: list[GraphViewNode] = field(default_factory=list)
    edges: list[GraphViewEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"nodes": [asdict(n) for n in self.nodes], "edges": [asdict(e) for e in self.edges]}
