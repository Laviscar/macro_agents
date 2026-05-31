from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from view_models.timeline import NarrativeTimeline, TimelinePoint


def build_narrative_timeline(
    storage_root: Path,
    window_days: int | None = 30,
    key_only: bool = True,
) -> NarrativeTimeline:
    """Build the evolution timeline.

    `window_days` keeps only commits within the last N days (None = all). `key_only`
    keeps only genuinely significant nodes in the change log (strength moved, or a
    branch/challenge commit) — dropping 中性 no-change commits so it isn't an endless wall.
    The strength/confidence chart series still use every windowed commit.
    """
    mains = _load_json_documents(storage_root / "main_narrative_state")
    commits = sorted(
        _load_json_documents(storage_root / "narrative_commits"),
        key=lambda c: c.get("created_at", ""),
    )
    if window_days is not None and commits:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        commits = [c for c in commits if c.get("created_at", "") >= cutoff]

    if not mains and not commits:
        return NarrativeTimeline(available=False, title="", total_commits=0)

    title = ""
    if mains:
        main = next((m for m in mains if m.get("id") == "main_default"), None)
        if main is None:
            main = max(mains, key=lambda m: m.get("updated_at", ""))
        title = main.get("title", "")

    points: list[TimelinePoint] = []
    labels: list[str] = []
    strength_series: list[float] = []
    confidence_series: list[float] = []

    current_strength = _seed_value(commits, "strength")
    current_confidence = _seed_value(commits, "confidence")
    if commits:
        labels.append("start")
        strength_series.append(current_strength)
        confidence_series.append(current_confidence)

    for commit in commits:
        changes = commit.get("field_changes", {})
        strength = changes.get("strength") if isinstance(changes.get("strength"), dict) else None
        confidence = changes.get("confidence") if isinstance(changes.get("confidence"), dict) else None

        s_from = float(strength["from"]) if strength and "from" in strength else None
        s_to = float(strength["to"]) if strength and "to" in strength else None
        c_from = float(confidence["from"]) if confidence and "from" in confidence else None
        c_to = float(confidence["to"]) if confidence and "to" in confidence else None

        if s_to is not None:
            current_strength = s_to
        if c_to is not None:
            current_confidence = c_to

        labels.append(commit.get("created_at", ""))
        strength_series.append(current_strength)
        confidence_series.append(current_confidence)

        points.append(
            TimelinePoint(
                when=commit.get("created_at", ""),
                summary=commit.get("summary", ""),
                narrative_type=commit.get("narrative_type", "main"),
                direction=_direction(s_from, s_to, commit.get("narrative_type", "main")),
                strength_from=s_from,
                strength_to=s_to,
                confidence_from=c_from,
                confidence_to=c_to,
                evidence_count=len(commit.get("source_evidence_ids", [])),
            )
        )

    points.reverse()  # newest first for the change log

    if key_only:
        # A node is "key" when strength actually moved, or it's a branch/challenge commit.
        # No-change 中性 main commits are noise in the change log.
        points = [p for p in points if p.direction != "中性" or p.narrative_type == "branch"]

    return NarrativeTimeline(
        available=bool(commits),
        title=title,
        total_commits=len(commits),
        key_count=len(points),
        points=points,
        series_labels=labels,
        strength_series=strength_series,
        confidence_series=confidence_series,
    )


def _seed_value(commits: list[dict], key: str) -> float:
    """Starting level = first commit's 'from' for the field, else 0.5."""
    for commit in commits:
        change = commit.get("field_changes", {}).get(key)
        if isinstance(change, dict) and "from" in change:
            return float(change["from"])
    return 0.5


def _direction(s_from: float | None, s_to: float | None, narrative_type: str) -> str:
    if s_from is not None and s_to is not None:
        delta = s_to - s_from
        return "强化" if delta > 0 else ("削弱" if delta < 0 else "中性")
    if narrative_type == "branch":
        return "挑战"
    return "中性"


def _load_json_documents(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]
