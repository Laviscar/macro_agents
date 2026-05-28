from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class NewsListItem:
    news_item_id: int
    title: str
    source_name: str
    published_at: str | None
    analysis_status: str
    summary: str


@dataclass(slots=True)
class AnalysisSummaryCard:
    analysis_card_id: str
    thesis: str
    mainline_relation: str
    confidence: float
    created_at: str


@dataclass(slots=True)
class EvidenceSummaryCard:
    evidence_id: str
    claim: str
    relation_type: str
    why: str
    counter_evidence: list[str]
    target_main_narrative_id: str | None
    target_branch_id: str | None
    created_at: str


@dataclass(slots=True)
class NewsDetailView:
    news: NewsListItem
    analysis: AnalysisSummaryCard | None
    evidence_items: list[EvidenceSummaryCard]
