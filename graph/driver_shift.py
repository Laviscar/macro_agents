from __future__ import annotations

from pydantic import BaseModel

from schemas.graph_edge import GraphEdge

DEFAULT_MIN_DOMINANT_WEIGHT = 0.15
DEFAULT_CONTESTED_GAP = 0.10


class DriverShift(BaseModel):
    """A detected change in an asset's dominant driver (the core 'driver switch' event)."""

    node_id: str
    from_driver: str
    to_driver: str
    at: str


def dominant_edge(incoming_edges: list[GraphEdge], min_weight: float = DEFAULT_MIN_DOMINANT_WEIGHT) -> GraphEdge | None:
    """The strongest incoming edge, or None if even the strongest is below threshold."""
    if not incoming_edges:
        return None
    top = max(incoming_edges, key=lambda e: e.weight)
    return top if top.weight >= min_weight else None


def detect_shift(node_id: str, prev_driver: str | None, new_driver: str | None, at: str) -> DriverShift | None:
    """Emit a shift only when an established dominant driver changes identity.

    First-time establishment (prev=None) or losing dominance entirely (new=None)
    is not a 'switch'.
    """
    if prev_driver is None or new_driver is None:
        return None
    if prev_driver == new_driver:
        return None
    return DriverShift(node_id=node_id, from_driver=prev_driver, to_driver=new_driver, at=at)


def contested(incoming_edges: list[GraphEdge], gap: float = DEFAULT_CONTESTED_GAP) -> bool:
    """True when the runner-up driver is within `gap` of the leader (approaching a shift)."""
    if len(incoming_edges) < 2:
        return False
    weights = sorted((e.weight for e in incoming_edges), reverse=True)
    return (weights[0] - weights[1]) < gap
