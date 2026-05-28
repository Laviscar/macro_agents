from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AnalystOpsCard:
    processed_news_count: int
    analyzed_count: int
    skipped_count: int
    error_count: int
    evidence_generated_count: int
    latest_run_at: str | None
    status_text: str


@dataclass(slots=True)
class NarrativeManagerOpsCard:
    main_updates_count: int
    branch_updates_count: int
    commit_count: int
    alert_count: int
    latest_run_at: str | None
    status_text: str


@dataclass(slots=True)
class PipelineHealthCard:
    pending_sort_count: int
    pending_analysis_count: int
    analyzed_count: int
    skipped_count: int
    error_count: int
    latest_fetch_at: str | None
    latest_analysis_at: str | None


@dataclass(slots=True)
class OperationsOverview:
    analyst: AnalystOpsCard
    narrative_manager: NarrativeManagerOpsCard
    pipeline_health: PipelineHealthCard
