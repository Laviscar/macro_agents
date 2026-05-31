from __future__ import annotations

import json
from pathlib import Path

from view_models.research_overview import ChallengeBranchCard, MainNarrativeCard, ResearchOverview


def build_research_overview(storage_root: Path, repository=None) -> ResearchOverview:
    main_narratives = _load_json_documents(storage_root / "main_narrative_state")
    branch_narratives = _load_json_documents(storage_root / "branch_narrative_state")
    alerts = [item for item in _load_json_documents(storage_root / "alerts") if item.get("status") is None]
    alert_status = next((item for item in _load_json_documents(storage_root / "alerts") if item.get("status") is not None), None)

    main_cards: list[MainNarrativeCard] = []
    for narrative in _sort_records(main_narratives, "updated_at"):
        challenge_count = sum(
            1 for branch in branch_narratives if branch.get("parent_main_narrative_id") == narrative["id"]
        )
        main_cards.append(
            MainNarrativeCard(
                narrative_id=narrative["id"],
                title=narrative["title"],
                status=narrative["status"],
                headline=_build_main_headline(narrative, challenge_count),
                summary=_build_main_summary(narrative),
                strength=float(narrative["strength"]),
                confidence=float(narrative["confidence"]),
                reinforcing_factors=_recent_evidence_claims(narrative.get("supporting_evidence", []), repository),
                fragility_factors=list(narrative.get("fragility", []))[-5:],
                challenge_count=challenge_count,
                watch_items=list(narrative.get("watch_items", []))[-5:],
                updated_at=narrative["updated_at"],
            )
        )

    challenge_cards = [
        ChallengeBranchCard(
            branch_id=branch["id"],
            title=branch["title"],
            status=branch["status"],
            headline=_build_branch_headline(branch),
            challenge_probability=float(branch["challenge_probability"]),
            supporting_factors=list(branch.get("supporting_evidence", [])),
            key_triggers=list(branch.get("key_triggers", [])),
            parent_main_narrative_id=branch["parent_main_narrative_id"],
            updated_at=branch["updated_at"],
        )
        for branch in _sort_records(branch_narratives, "updated_at")
    ]

    latest_updated_at = max(
        [card.updated_at for card in main_cards] + [card.updated_at for card in challenge_cards] + [""],
    )
    global_headline = _build_global_headline(main_cards, challenge_cards, alerts, alert_status)
    global_summary = _build_global_summary(main_cards, challenge_cards)

    return ResearchOverview(
        main_cards=main_cards,
        challenge_branches=challenge_cards,
        global_headline=global_headline,
        global_summary=global_summary,
        updated_at=latest_updated_at,
    )


def _recent_evidence_claims(evidence_ids: list, repository, limit: int = 5) -> list[str]:
    """Resolve the most recent supporting-evidence IDs to readable claim text.
    Falls back to the raw IDs when no repository is available (back-compat)."""
    recent = list(evidence_ids)[-limit:]
    if not recent or repository is None:
        return recent
    claims = repository.get_evidence_claims(recent)
    # preserve recent order; drop IDs we couldn't resolve
    return [claims[eid] for eid in recent if eid in claims]


def _load_json_documents(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]


def _sort_records(records: list[dict], key: str) -> list[dict]:
    return sorted(records, key=lambda item: item.get(key, ""), reverse=True)


def _build_main_headline(narrative: dict, challenge_count: int) -> str:
    return (
        f"{narrative['title']} 当前稳固度 {round(float(narrative['strength']) * 100)}%，"
        f"关联挑战分支 {challenge_count} 个。"
    )


def _build_main_summary(narrative: dict) -> str:
    if narrative.get("watch_items"):
        return f"当前最值得盯的是：{', '.join(narrative['watch_items'][:3])}"
    if narrative.get("fragility"):
        return f"主线脆弱点包括：{', '.join(narrative['fragility'][:3])}"
    return "当前主线暂无额外 watch items。"


def _build_branch_headline(branch: dict) -> str:
    return (
        f"{branch['title']} 当前处于 {branch['status']} 状态，挑战概率 "
        f"{round(float(branch['challenge_probability']) * 100)}%。"
    )


def _build_global_headline(
    main_cards: list[MainNarrativeCard],
    challenge_cards: list[ChallengeBranchCard],
    alerts: list[dict],
    alert_status: dict | None,
) -> str:
    if not main_cards:
        return "当前还没有可展示的主线叙事。"
    lead = main_cards[0]
    if alerts:
        return f"当前主线是 {lead.title}，并且已经出现需要注意的挑战提醒。"
    if challenge_cards:
        return f"当前主线是 {lead.title}，已有 {len(challenge_cards)} 个挑战分支进入观察。"
    if alert_status:
        return f"当前主线是 {lead.title}。{alert_status.get('message', '')}"
    return f"当前主线是 {lead.title}。"


def _build_global_summary(
    main_cards: list[MainNarrativeCard],
    challenge_cards: list[ChallengeBranchCard],
) -> str:
    if not main_cards:
        return "Research 首页暂无内容。"
    lead = main_cards[0]
    return (
        f"主线稳固度 {round(lead.strength * 100)}%，判断置信度 {round(lead.confidence * 100)}%，"
        f"当前挑战分支 {len(challenge_cards)} 个。"
    )
