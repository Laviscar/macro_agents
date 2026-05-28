from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class IngestionRunSummary:
    source_count: int
    failed_source_count: int
    payload_seen_count: int
    normalized_seen_count: int
    inserted_count: int
    deduped_count: int
    invalid_payload_count: int
    enabled_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class IngestionStatusSummary:
    pending_sort_count: int
    pending_analysis_count: int
    analyzed_count: int
    skipped_count: int
    error_count: int


@dataclass(slots=True)
class IngestionCleaningSummary:
    resource_card_count: int
    average_analysis_readiness_score: float | None
    route_distribution: dict[str, int]
    route_percentages: dict[str, float]
    source_distribution: dict[str, int]
    latest_titles: list[str]


@dataclass(slots=True)
class IngestionSourceRunCard:
    source_name: str
    source_type: str
    payload_seen_count: int
    normalized_seen_count: int
    inserted_count: int
    deduped_count: int
    invalid_payload_count: int
    failed: bool
    error_message: str | None


@dataclass(slots=True)
class IngestionSampleCard:
    news_item_id: int
    title: str
    source_name: str
    analysis_status: str
    raw_news: dict
    resource_card: dict | None


@dataclass(slots=True)
class IngestionFailureCard:
    source_name: str
    error_message: str


@dataclass(slots=True)
class IngestionQABadPayloadCard:
    source_name: str
    reason: str
    payload: dict


@dataclass(slots=True)
class IngestionQAOverview:
    report_available: bool
    headline: str
    summary: str
    generated_at: str | None
    run_summary: IngestionRunSummary
    status_summary: IngestionStatusSummary
    cleaning_summary: IngestionCleaningSummary
    source_runs: list[IngestionSourceRunCard]
    samples: list[IngestionSampleCard]
    failures: list[IngestionFailureCard]
    bad_payloads: list[IngestionQABadPayloadCard]
