from __future__ import annotations

import json
from pathlib import Path

from repositories.news_repository import SQLiteNewsRepository
from view_models.operations_overview import (
    AnalystOpsCard,
    NarrativeManagerOpsCard,
    OperationsOverview,
    PipelineHealthCard,
)


def build_operations_overview(
    repository: SQLiteNewsRepository,
    storage_root: Path,
) -> OperationsOverview:
    status_counts = repository.get_status_counts()
    narrative_commits = _load_json_documents(storage_root / "narrative_commits")
    alerts = [item for item in _load_json_documents(storage_root / "alerts") if item.get("status") is None]
    branch_narratives = _load_json_documents(storage_root / "branch_narrative_state")
    main_narratives = _load_json_documents(storage_root / "main_narrative_state")

    news_rows = repository.list_news_items(limit=200)
    latest_fetch_at = max((row.get("fetched_at") or "" for row in news_rows), default=None) or None
    latest_analysis_at = repository.get_latest_analysis_created_at()

    analyst = AnalystOpsCard(
        processed_news_count=status_counts.get("analyzed", 0) + status_counts.get("skipped", 0) + status_counts.get("error", 0),
        analyzed_count=status_counts.get("analyzed", 0),
        skipped_count=status_counts.get("skipped", 0),
        error_count=status_counts.get("error", 0),
        evidence_generated_count=repository.count_evidence_records(),
        latest_run_at=latest_analysis_at,
        status_text=_build_analyst_status_text(status_counts),
    )

    narrative_manager = NarrativeManagerOpsCard(
        main_updates_count=sum(1 for item in narrative_commits if item.get("narrative_type") == "main"),
        branch_updates_count=sum(1 for item in narrative_commits if item.get("narrative_type") == "branch"),
        commit_count=len(narrative_commits),
        alert_count=len(alerts),
        latest_run_at=max((item.get("created_at") or "" for item in narrative_commits), default=None) or None,
        status_text=_build_narrative_status_text(narrative_commits, alerts, main_narratives, branch_narratives),
    )

    pipeline_health = PipelineHealthCard(
        pending_sort_count=status_counts.get("pending_sort", 0),
        pending_analysis_count=status_counts.get("pending_analysis", 0),
        analyzed_count=status_counts.get("analyzed", 0),
        skipped_count=status_counts.get("skipped", 0),
        error_count=status_counts.get("error", 0),
        latest_fetch_at=latest_fetch_at,
        latest_analysis_at=latest_analysis_at,
    )

    return OperationsOverview(
        analyst=analyst,
        narrative_manager=narrative_manager,
        pipeline_health=pipeline_health,
    )


def _load_json_documents(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]
def _build_analyst_status_text(status_counts: dict[str, int]) -> str:
    if status_counts.get("error", 0) > 0:
        return f"Analyst 当前有 {status_counts['error']} 条错误记录，需要优先排查。"
    pending = status_counts.get("pending_sort", 0) + status_counts.get("pending_analysis", 0)
    if pending > 0:
        return f"Analyst 正常运行中，但还有 {pending} 条待处理新闻。"
    return "Analyst 当前没有积压或错误。"


def _build_narrative_status_text(
    commits: list[dict],
    alerts: list[dict],
    main_narratives: list[dict],
    branch_narratives: list[dict],
) -> str:
    if not commits:
        return "Narrative Manager 还没有产出 commit。"
    if alerts:
        return f"Narrative Manager 当前有 {len(alerts)} 条 challenge alert 需要关注。"
    return (
        f"Narrative Manager 当前维护 {len(main_narratives)} 条 main 和 "
        f"{len(branch_narratives)} 条 branch，最近运行正常。"
    )
