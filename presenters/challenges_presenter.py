from __future__ import annotations

import json
from pathlib import Path

from view_models.challenges import AlertItem, ChallengeItem, ChallengesOverview, ScenarioView

_ALERT_CAP = 8       # 预警去重后最多显示条数
_CHALLENGE_CAP = 10  # 挑战分支去重后最多显示条数


def build_challenges_overview(storage_root: Path) -> ChallengesOverview:
    branches = _load_json_documents(storage_root / "branch_narrative_state")
    alert_docs = [doc for doc in _load_json_documents(storage_root / "alerts") if "challenged_claim" in doc]
    scenarios = _load_json_documents(storage_root / "scenarios")

    if not branches and not alert_docs:
        return ChallengesOverview(available=False, headline="当前没有挑战分支或预警。")

    branch_title_by_id = {b.get("id"): b.get("title", "") for b in branches}
    scenario_by_branch = {s.get("branch_narrative_id"): s for s in scenarios}

    # Dedupe alerts by (challenged_claim, branch) keeping the highest-probability instance —
    # the old pipeline emitted one alert per consolidation tick on the same fixed claim, so
    # the page filled with 20+ identical rows.
    best_alert: dict[tuple, dict] = {}
    for doc in alert_docs:
        key = (doc.get("challenged_claim", ""), doc.get("branch_narrative_id"))
        prob = float(doc.get("challenge_probability", 0.0))
        if key not in best_alert or prob > float(best_alert[key].get("challenge_probability", 0.0)):
            best_alert[key] = doc
    total_alerts = len(best_alert)
    alerts = [
        AlertItem(
            challenged_claim=doc.get("challenged_claim", ""),
            challenge_probability=float(doc.get("challenge_probability", 0.0)),
            branch_title=branch_title_by_id.get(doc.get("branch_narrative_id"), ""),
            key_triggers=list(doc.get("key_triggers", [])),
            created_at=doc.get("created_at", ""),
        )
        for doc in sorted(best_alert.values(), key=lambda d: float(d.get("challenge_probability", 0.0)), reverse=True)
    ][:_ALERT_CAP]

    # Dedupe branches by title keeping the highest-probability one — many duplicate-title
    # branches were opened and never merged.
    best_branch: dict[str, dict] = {}
    for branch in branches:
        title = branch.get("title", "")
        prob = float(branch.get("challenge_probability", 0.0))
        if title not in best_branch or prob > float(best_branch[title].get("challenge_probability", 0.0)):
            best_branch[title] = branch
    total_challenges = len(best_branch)

    challenges = []
    deduped_branches = sorted(
        best_branch.values(), key=lambda b: float(b.get("challenge_probability", 0.0)), reverse=True
    )[:_CHALLENGE_CAP]
    for branch in deduped_branches:
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

    headline = _build_headline(total_challenges, total_alerts, challenges)
    return ChallengesOverview(
        available=True,
        headline=headline,
        alerts=alerts,
        challenges=challenges,
        total_alerts=total_alerts,
        total_challenges=total_challenges,
    )


def _build_headline(total_challenges: int, total_alerts: int, challenges: list[ChallengeItem]) -> str:
    if not challenges and total_alerts == 0:
        return "当前没有挑战分支或预警。"
    top_prob = max((c.challenge_probability for c in challenges), default=0.0)
    return (
        f"共 {total_challenges} 条挑战分支，{total_alerts} 条已触发预警，"
        f"最高挑战概率 {round(top_prob * 100)}%。"
    )


def _load_json_documents(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]
