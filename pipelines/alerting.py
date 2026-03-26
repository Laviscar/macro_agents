from __future__ import annotations

from schemas.challenge_alert import ChallengeAlert


def extract_alerts(narrative_state: dict) -> list[ChallengeAlert]:
    return list(narrative_state.get("alerts", []))
