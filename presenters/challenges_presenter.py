from __future__ import annotations

import json
from pathlib import Path

from view_models.challenges import AlertItem, ChallengeItem, ChallengesOverview, ScenarioView


def build_challenges_overview(storage_root: Path) -> ChallengesOverview:
    branches = _load_json_documents(storage_root / "branch_narrative_state")
    alert_docs = [doc for doc in _load_json_documents(storage_root / "alerts") if "challenged_claim" in doc]
    scenarios = _load_json_documents(storage_root / "scenarios")

    if not branches and not alert_docs:
        return ChallengesOverview(available=False, headline="当前没有挑战分支或预警。")

    branch_title_by_id = {b.get("id"): b.get("title", "") for b in branches}
    scenario_by_branch = {s.get("branch_narrative_id"): s for s in scenarios}

    alerts = [
        AlertItem(
            challenged_claim=doc.get("challenged_claim", ""),
            challenge_probability=float(doc.get("challenge_probability", 0.0)),
            branch_title=branch_title_by_id.get(doc.get("branch_narrative_id"), ""),
            key_triggers=list(doc.get("key_triggers", [])),
            created_at=doc.get("created_at", ""),
        )
        for doc in sorted(alert_docs, key=lambda d: float(d.get("challenge_probability", 0.0)), reverse=True)
    ]

    challenges = []
    for branch in sorted(branches, key=lambda b: float(b.get("challenge_probability", 0.0)), reverse=True):
        scenario_doc = scenario_by_branch.get(branch.get("id"))
        scenario = None
        if scenario_doc:
            split = scenario_doc.get("probability_split", {})
            scenario = ScenarioView(
                scenario_a_name=scenario_doc.get("scenario_a_name", "主线延续"),
                scenario_a_prob=float(split.get("scenario_a", 0.0)),
                scenario_b_name=scenario_doc.get("scenario_b_name", "分支上位"),
                scenario_b_prob=float(split.get("scenario_b", 0.0)),
            )
        challenges.append(
            ChallengeItem(
                branch_id=branch.get("id", ""),
                title=branch.get("title", ""),
                status=branch.get("status", ""),
                challenge_probability=float(branch.get("challenge_probability", 0.0)),
                branch_strength=float(branch.get("branch_strength", 0.0)),
                core_claims=list(branch.get("core_claims", [])),
                key_triggers=list(branch.get("key_triggers", [])),
                supporting_evidence_count=len(branch.get("supporting_evidence", [])),
                scenario=scenario,
            )
        )

    headline = _build_headline(challenges, alerts)
    return ChallengesOverview(available=True, headline=headline, alerts=alerts, challenges=challenges)


def _build_headline(challenges: list[ChallengeItem], alerts: list[AlertItem]) -> str:
    if not challenges and not alerts:
        return "当前没有挑战分支或预警。"
    top_prob = max((c.challenge_probability for c in challenges), default=0.0)
    return (
        f"共 {len(challenges)} 条挑战分支，{len(alerts)} 条已触发预警，"
        f"最高挑战概率 {round(top_prob * 100)}%。"
    )


def _load_json_documents(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]
