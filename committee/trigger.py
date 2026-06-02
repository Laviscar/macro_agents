from __future__ import annotations

from schemas.committee import PendingConvocation
from utils.clock import now_iso


def crossed_levels(ratio: float, prev_highest: float, levels: list[float]) -> tuple[list[float], float]:
    """Proximity bands newly crossed upward since prev_highest, and the new highest band.

    A band fires once; re-firing requires the caller to reset prev_highest (hysteresis,
    done when ratio drops below the lowest band)."""
    newly = [lv for lv in sorted(levels) if lv > prev_highest and ratio >= lv]
    highest = max([prev_highest, *newly]) if newly else prev_highest
    return newly, highest


def velocity_fired(delta: float, threshold: float, already_fired: bool) -> bool:
    """Fire when the challenger's per-cycle weight gain crosses threshold and we haven't
    already fired for this run-up. Caller clears `already_fired` once delta falls back
    below threshold (hysteresis)."""
    return (not already_fired) and delta >= threshold


def evaluate_assets(graph_repo, state: dict, levels: list[float], velocity_delta: float) -> list[PendingConvocation]:
    """For each contested active asset, emit proximity / velocity pending convocations.

    `state` (mutated in place) holds per-asset {"highest": float, "vel_fired": bool} for
    debouncing across runs."""
    out: list[PendingConvocation] = []
    for node in graph_repo.list_nodes():
        if node.kind != "asset" or node.status != "active":
            continue
        edges = sorted(graph_repo.incoming_edges(node.id), key=lambda e: e.weight, reverse=True)
        if len(edges) < 2 or sum(len(e.supporting_evidence) for e in edges) == 0 or edges[0].weight <= 0:
            continue
        leader, runner = edges[0], edges[1]
        ratio = runner.weight / leader.weight
        st = state.setdefault(node.id, {"highest": 0.0, "vel_fired": False})
        if ratio < min(levels):
            st["highest"] = 0.0
        new_bands, st["highest"] = crossed_levels(ratio, st["highest"], levels)
        base = dict(asset_id=node.id, asset_name=node.name, ratio=round(ratio, 3),
                    leader=leader.driver_label, runner_up=runner.driver_label,
                    is_reversal=leader.sign != runner.sign, created_at=now_iso())
        for lv in new_bands:
            out.append(PendingConvocation(trigger="proximity", level=lv, **base))
        delta = runner.weight - runner.weight_prev
        if delta < velocity_delta:
            st["vel_fired"] = False
        elif velocity_fired(delta, velocity_delta, st["vel_fired"]):
            st["vel_fired"] = True
            out.append(PendingConvocation(trigger="velocity", velocity_delta=round(delta, 3), **base))
    return out
