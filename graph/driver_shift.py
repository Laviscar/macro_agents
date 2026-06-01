from __future__ import annotations

import os

from pydantic import BaseModel

from schemas.graph_edge import GraphEdge

DEFAULT_MIN_DOMINANT_WEIGHT = 0.15
DEFAULT_CONTESTED_GAP = 0.10


def _env_float(key: str, default: float, override: float | None) -> float:
    if override is not None:
        return override
    try:
        return float(os.environ.get(key) or default)
    except ValueError:
        return default


class DriverShift(BaseModel):
    """A detected change in an asset's dominant driver (the core 'driver switch' event)."""

    node_id: str
    from_driver: str
    to_driver: str
    at: str


def dominant_edge(incoming_edges: list[GraphEdge], min_weight: float | None = None) -> GraphEdge | None:
    """The strongest incoming edge, or None if even the strongest is below threshold
    (DRIVER_MIN_DOMINANT_WEIGHT env, default 0.15)."""
    if not incoming_edges:
        return None
    mw = _env_float("DRIVER_MIN_DOMINANT_WEIGHT", DEFAULT_MIN_DOMINANT_WEIGHT, min_weight)
    top = max(incoming_edges, key=lambda e: e.weight)
    return top if top.weight >= mw else None


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


def contested(incoming_edges: list[GraphEdge], gap: float | None = None) -> bool:
    """True when the runner-up driver is within `gap` of the leader (approaching a shift;
    DRIVER_CONTESTED_GAP env, default 0.10)."""
    if len(incoming_edges) < 2:
        return False
    g = _env_float("DRIVER_CONTESTED_GAP", DEFAULT_CONTESTED_GAP, gap)
    weights = sorted((e.weight for e in incoming_edges), reverse=True)
    return (weights[0] - weights[1]) < g
