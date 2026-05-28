from __future__ import annotations

import json
from typing import Any

from repositories.news_repository import SQLiteNewsRepository
from view_models.warehouse_detail import (
    AnalysisSummaryCard,
    EvidenceSummaryCard,
    NewsDetailView,
    NewsListItem,
)


def build_news_list_items(rows: list[dict[str, Any]]) -> list[NewsListItem]:
    return [
        NewsListItem(
            news_item_id=int(row["id"]),
            title=str(row["title"]),
            source_name=str(row["source_name"]),
            published_at=row.get("published_at"),
            analysis_status=str(row["analysis_status"]),
            summary=_short_summary(str(row.get("summary") or "")),
        )
        for row in rows
    ]


def build_news_detail_view(repository: SQLiteNewsRepository, row: dict[str, Any]) -> NewsDetailView:
    list_item = build_news_list_items([row])[0]
    analysis_cards = repository.get_analysis_cards_for_news_item(list_item.news_item_id)
    evidence_items = repository.get_evidence_for_news_item(list_item.news_item_id)

    analysis = None
    if analysis_cards:
        first = analysis_cards[0]
        analysis = AnalysisSummaryCard(
            analysis_card_id=first.id,
            thesis=first.thesis,
            mainline_relation=first.mainline_relation,
            confidence=first.confidence,
            created_at=first.created_at,
        )

    evidence_cards = [
        EvidenceSummaryCard(
            evidence_id=item.id,
            claim=item.claim,
            relation_type=item.relation_type,
            why=item.why,
            counter_evidence=list(item.counter_evidence),
            target_main_narrative_id=item.target_main_narrative_id,
            target_branch_id=item.target_branch_id,
            created_at=item.created_at,
        )
        for item in evidence_items
    ]

    return NewsDetailView(
        news=list_item,
        analysis=analysis,
        evidence_items=evidence_cards,
    )


def build_debug_payload(repository: SQLiteNewsRepository, row: dict[str, Any]) -> dict[str, Any]:
    analysis_cards = repository.get_analysis_cards_for_news_item(int(row["id"]))
    evidence_items = repository.get_evidence_for_news_item(int(row["id"]))
    payload: dict[str, Any] = {
        "news_item": {
            "id": row["id"],
            "title": row["title"],
            "source_name": row["source_name"],
            "summary": row["summary"],
            "status": row["analysis_status"],
            "published_at": row["published_at"],
            "fetched_at": row["fetched_at"],
        }
    }
    if row.get("resource_card_json"):
        payload["resource_card"] = json.loads(row["resource_card_json"])
    if analysis_cards:
        payload["analysis"] = analysis_cards[0].model_dump(mode="json")
    if evidence_items:
        payload["evidence_items"] = [item.model_dump(mode="json") for item in evidence_items]
    return payload


def _short_summary(summary: str) -> str:
    cleaned = summary.strip()
    if not cleaned:
        return "暂无摘要。"
    return cleaned if len(cleaned) <= 140 else f"{cleaned[:137].rstrip()}..."
