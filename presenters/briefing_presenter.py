from __future__ import annotations

import json
from pathlib import Path

from view_models.briefing import BriefingBranch, BriefingChange, BriefingOverview


def build_briefing_overview(storage_root: Path) -> BriefingOverview:
    mains = _load_json_documents(storage_root / "main_narrative_state")
    if not mains:
        return BriefingOverview(
            available=False, title="", status="", read_line="",
            strength=0.0, confidence=0.0, strength_delta=None, confidence_delta=None,
        )

    main = next((m for m in mains if m.get("id") == "main_default"), None)
    if main is None:
        main = max(mains, key=lambda m: m.get("updated_at", ""))

    commits = sorted(
        _load_json_documents(storage_root / "narrative_commits"),
        key=lambda c: c.get("created_at", ""),
    )

    strength_series, strength_delta, confidence_delta = _series_and_deltas(commits)
    if not strength_series:
        strength_series = [float(main["strength"])]

    recent_changes = _recent_changes(commits)

    branches = sorted(
        _load_json_documents(storage_root / "branch_narrative_state"),
        key=lambda b: float(b.get("challenge_probability", 0.0)),
        reverse=True,
    )
    top_branches = [
        BriefingBranch(
            title=b["title"],
            challenge_probability=float(b["challenge_probability"]),
            key_triggers=list(b.get("key_triggers", [])),
        )
        for b in branches[:2]
    ]

    return BriefingOverview(
        available=True,
        title=main["title"],
        status=main["status"],
        read_line=main.get("read_line", "") or "",
        strength=float(main["strength"]),
        confidence=float(main["confidence"]),
        strength_delta=strength_delta,
        confidence_delta=confidence_delta,
        strength_series=strength_series,
        recent_changes=recent_changes,
        top_branches=top_branches,
        updated_at=main.get("updated_at", ""),
    )


def _series_and_deltas(commits: list[dict]) -> tuple[list[float], float | None, float | None]:
    series: list[float] = []
    strength_delta: float | None = None
    confidence_delta: float | None = None
    for commit in commits:
        changes = commit.get("field_changes", {})
        strength = changes.get("strength")
        if isinstance(strength, dict) and "to" in strength:
            if not series and "from" in strength:
                series.append(float(strength["from"]))
            series.append(float(strength["to"]))
            if "from" in strength:
                strength_delta = float(strength["to"]) - float(strength["from"])
        confidence = changes.get("confidence")
        if isinstance(confidence, dict) and "from" in confidence and "to" in confidence:
            confidence_delta = float(confidence["to"]) - float(confidence["from"])
    return series, strength_delta, confidence_delta


def _recent_changes(commits: list[dict], limit: int = 5) -> list[BriefingChange]:
    changes: list[BriefingChange] = []
    for commit in reversed(commits[-limit:]):
        field_changes = commit.get("field_changes", {})
        direction = "中性"
        strength = field_changes.get("strength")
        if isinstance(strength, dict) and "from" in strength and "to" in strength:
            delta = float(strength["to"]) - float(strength["from"])
            direction = "强化" if delta > 0 else ("削弱" if delta < 0 else "中性")
        elif commit.get("narrative_type") == "branch":
            direction = "挑战"
        changes.append(
            BriefingChange(
                when=commit.get("created_at", ""),
                summary=commit.get("summary", ""),
                direction=direction,
            )
        )
    return changes


def _load_json_documents(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]
