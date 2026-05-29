from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class EvalMetrics:
    session_count: int
    narrative_stability: float
    evidence_precision: float
    challenge_hit_rate: float
    latency_seconds: float
    tokens_used: int


def compute_metrics(
    sessions: list[dict],
    events_by_session: dict[str, list[dict]],
) -> EvalMetrics:
    n = len(sessions)
    if n == 0:
        return EvalMetrics(0, 0.0, 0.0, 0.0, 0.0, 0)

    def _narrative_id(session: dict) -> str | None:
        rj = session.get("result_json")
        if not rj:
            return None
        try:
            return json.loads(rj).get("main_narrative_id")
        except Exception:
            return None

    if n == 1:
        stability = 1.0
    else:
        ids = [_narrative_id(s) for s in sessions]
        stable_pairs = sum(1 for a, b in zip(ids, ids[1:]) if a is not None and a == b)
        stability = stable_pairs / (n - 1)

    precision_ok = 0
    precision_total = 0
    hit_ok = 0
    hit_total = 0
    total_latency = 0.0
    total_tokens = 0

    for sess_events in events_by_session.values():
        has_plan = False
        has_evidence = False
        high_confidence = False
        has_observe = False

        for event in sess_events:
            etype = event.get("event_type", "")
            raw = event.get("payload_json", "{}")
            try:
                payload = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                payload = {}

            if etype == "observe_result":
                has_observe = True
                high_confidence = payload.get("avg_confidence", 0.0) >= 0.7
                has_evidence = payload.get("evidence_count", 0) > 0
            elif etype == "plan_decided":
                has_plan = bool(payload.get("planned_tools"))
            elif etype == "budget_check":
                total_latency += payload.get("elapsed_seconds", 0.0)
                total_tokens += payload.get("tokens_used", 0)

        if has_observe:
            precision_total += 1
            if high_confidence:
                precision_ok += 1
        if has_plan:
            hit_total += 1
            if has_evidence:
                hit_ok += 1

    precision = precision_ok / precision_total if precision_total > 0 else 0.0
    hit_rate = hit_ok / hit_total if hit_total > 0 else 0.0
    avg_latency = total_latency / n

    return EvalMetrics(
        session_count=n,
        narrative_stability=round(stability, 4),
        evidence_precision=round(precision, 4),
        challenge_hit_rate=round(hit_rate, 4),
        latency_seconds=round(avg_latency, 4),
        tokens_used=total_tokens,
    )
