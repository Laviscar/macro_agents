from __future__ import annotations

import math
from datetime import datetime

from schemas.graph_edge import EdgeEvidenceRef, GraphEdge

DEFAULT_HALF_LIFE_DAYS = 14.0


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def decayed_contribution(ref: EdgeEvidenceRef, now: datetime, half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    """Evidence contribution decayed by age: contrib * 0.5 ** (age_days / half_life)."""
    age_days = max(0.0, (now - _parse(ref.created_at)).total_seconds() / 86400.0)
    return ref.contribution * (0.5 ** (age_days / half_life_days))


def compute_edge_weight(edge: GraphEdge, now: datetime, half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    """Edge weight from decayed evidence, squashed to [0,1) — replaces additive accumulation.

    weight = 1 - exp(-Σ decayed_contributions). More fresh evidence -> stronger,
    but bounded; old evidence fades automatically.
    """
    total = sum(decayed_contribution(ref, now, half_life_days) for ref in edge.supporting_evidence)
    return 1.0 - math.exp(-total)


def compute_node_strength(incoming_edges: list[GraphEdge]) -> tuple[float, float]:
    """Node strength = sigmoid(Σ sign*weight) mapped to [0,1] (0.5 = neutral).

    Confidence rises with total incoming evidence mass (bounded to 1).
    """
    if not incoming_edges:
        return 0.5, 0.5
    net = sum(edge.sign * edge.weight for edge in incoming_edges)
    strength = 1.0 / (1.0 + math.exp(-net))
    # confidence: average incoming edge weight as a proxy for how well-supported the node is
    mass = sum(edge.weight for edge in incoming_edges)
    confidence = min(1.0, mass / len(incoming_edges))
    return strength, confidence
