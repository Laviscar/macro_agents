from __future__ import annotations

import json

from agents.analyst import AnalystAgent
from agents.news_sorter import NewsSorterAgent
from pipelines.analyze import analyze_resource_cards
from pipelines.evidence_extract import extract_evidence_from_analysis
from repositories.news_repository import SQLiteNewsRepository
from schemas.resource_card import ResourceCard


def consume_pending_news(
    repository: SQLiteNewsRepository,
    sorter: NewsSorterAgent,
    analyst: AnalystAgent,
    limit: int = 20,
    context: dict | None = None,
) -> dict[str, int]:
    analysis_context = {"target_main_narrative_id": "main_default", **(context or {})}
    pending_rows = repository.list_pending_news(limit=limit)

    processed = 0
    analyzed = 0
    skipped = 0
    errors = 0

    for row in pending_rows:
        processed += 1
        news_item_id = int(row["id"])
        try:
            resource_card = _load_or_build_resource_card(row, sorter)
            next_status = "pending_analysis" if resource_card.route_to_analysis else "skipped"
            repository.save_resource_card(news_item_id, resource_card, status=next_status)

            if not resource_card.route_to_analysis:
                skipped += 1
                continue

            analysis_cards = analyze_resource_cards([resource_card], analyst, context=analysis_context)
            evidence_list = extract_evidence_from_analysis(
                analysis_cards,
                analyst,
                context=analysis_context,
            )
            repository.save_analysis_bundle(news_item_id, analysis_cards[0], evidence_list)
            analyzed += 1
        except Exception as exc:
            repository.mark_error(news_item_id, str(exc))
            errors += 1

    return {
        "processed": processed,
        "analyzed": analyzed,
        "skipped": skipped,
        "errors": errors,
    }


def _load_or_build_resource_card(row: dict, sorter: NewsSorterAgent) -> ResourceCard:
    existing = row.get("resource_card_json")
    if existing:
        return ResourceCard.model_validate_json(existing)

    raw_payload = json.loads(row["raw_payload_json"])
    payload = dict(raw_payload)
    payload.setdefault("source", row["source_name"])
    payload.setdefault("url", row["url"])
    payload.setdefault("title", row["title"])
    payload.setdefault("summary", row["summary"])
    payload.setdefault("timestamp", row["published_at"] or row["fetched_at"])
    return sorter.process(payload)
