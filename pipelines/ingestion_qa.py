from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.analyst import AnalystAgent
from agents.news_sorter import NewsSorterAgent
from pipelines.db_consumer import consume_pending_news
from pipelines.live_ingest import SourcePollResult, fetch_and_store_source
from repositories.news_repository import SQLiteNewsRepository
from schemas.raw_news_item import RawNewsItem
from utils.clock import now_iso
from utils.io import write_json


APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QA_DB_PATH = APP_ROOT / "storage" / "qa" / "ingestion_qa.sqlite3"
DEFAULT_QA_REPORT_PATH = APP_ROOT / "storage" / "qa" / "ingestion_report.json"


@dataclass
class FixturePayloadSource:
    source_name: str
    payloads: list[dict[str, Any]]
    source_type: str = "fixture"

    def __post_init__(self) -> None:
        self.last_payload_seen = 0
        self.last_invalid_payload_count = 0
        self.last_invalid_payload_examples: list[dict[str, Any]] = []

    def fetch_latest(self) -> list[RawNewsItem]:
        self.last_payload_seen = len(self.payloads)
        self.last_invalid_payload_examples = []
        items: list[RawNewsItem] = []
        for payload in self.payloads:
            title = str(payload.get("title") or "").strip()
            url = str(payload.get("url") or "").strip()
            if not title or not url:
                self.last_invalid_payload_examples.append(
                    {
                        "reason": "missing title/url",
                        "payload": payload,
                    }
                )
                continue
            items.append(
                RawNewsItem(
                    source_type=self.source_type,
                    source_name=self.source_name,
                    external_id=str(payload.get("external_id") or url),
                    url=url,
                    title=title,
                    summary=str(payload.get("summary") or title),
                    published_at=payload.get("published_at"),
                    fetched_at=str(payload.get("fetched_at") or "2026-04-03T09:00:00+00:00"),
                    raw_payload={
                        "title": title,
                        "summary": str(payload.get("summary") or title),
                        "source": self.source_name,
                        "url": url,
                        "timestamp": payload.get("published_at") or payload.get("fetched_at") or "2026-04-03T09:00:00+00:00",
                        "published_at": payload.get("published_at"),
                        "region": payload.get("region", ["Global"]),
                        "theme": payload.get("theme", ["macro_regime"]),
                        "importance_score": payload.get("importance_score", 0.62),
                        "structural_score": payload.get("structural_score", 0.58),
                        "timeliness_score": payload.get("timeliness_score", 0.75),
                        "verifiability_score": payload.get("verifiability_score", 0.75),
                    },
                )
            )
        self.last_invalid_payload_count = len(self.last_invalid_payload_examples)
        return items


@dataclass
class FailingFixtureSource:
    source_name: str
    error_message: str
    source_type: str = "fixture"
    last_payload_seen: int = 0
    last_invalid_payload_count: int = 0
    last_invalid_payload_examples: list[dict[str, Any]] = None

    def __post_init__(self) -> None:
        self.last_invalid_payload_examples = []

    def fetch_latest(self) -> list[RawNewsItem]:
        raise RuntimeError(self.error_message)


def build_ingestion_qa_sources() -> list:
    return [
        FixturePayloadSource(
            source_name="fixture_macro_feed",
            payloads=[
                {
                    "external_id": "high-signal-1",
                    "url": "https://example.com/high-signal-1",
                    "title": "US CPI cools again",
                    "summary": "Inflation data came in softer than expected.",
                    "published_at": "2026-04-01T08:00:00+00:00",
                    "fetched_at": "2026-04-01T08:05:00+00:00",
                    "region": ["US"],
                    "theme": ["inflation"],
                    "importance_score": 0.92,
                    "structural_score": 0.88,
                    "verifiability_score": 0.91,
                },
                {
                    "external_id": "high-signal-1",
                    "url": "https://example.com/high-signal-1",
                    "title": "US CPI cools again",
                    "summary": "Inflation data came in softer than expected.",
                    "published_at": "2026-04-01T08:00:00+00:00",
                    "fetched_at": "2026-04-01T08:06:00+00:00",
                    "region": ["US"],
                    "theme": ["inflation"],
                    "importance_score": 0.92,
                    "structural_score": 0.88,
                    "verifiability_score": 0.91,
                },
                {
                    "external_id": "watchlist-1",
                    "url": "https://example.com/watchlist-1",
                    "title": "Regional demand signals remain mixed",
                    "summary": "Macro signals are mixed and require more observation.",
                    "published_at": "2026-04-01T09:00:00+00:00",
                    "fetched_at": "2026-04-01T09:05:00+00:00",
                    "importance_score": 0.55,
                    "structural_score": 0.46,
                    "verifiability_score": 0.5,
                },
                {
                    "external_id": "archive-1",
                    "url": "https://example.com/archive-1",
                    "title": "Small local policy note",
                    "summary": "A low-signal local item that should be archived only.",
                    "published_at": "2026-04-01T10:00:00+00:00",
                    "fetched_at": "2026-04-01T10:05:00+00:00",
                    "importance_score": 0.25,
                    "structural_score": 0.3,
                    "verifiability_score": 0.35,
                },
                {
                    "external_id": "invalid-1",
                    "title": "Broken payload without URL",
                    "summary": "This should be counted as malformed input.",
                    "published_at": "2026-04-01T11:00:00+00:00",
                },
            ],
        ),
        FailingFixtureSource(
            source_name="fixture_failing_source",
            error_message="simulated upstream failure",
        ),
    ]


def run_ingestion_qa(
    *,
    db_path: Path = DEFAULT_QA_DB_PATH,
    report_path: Path = DEFAULT_QA_REPORT_PATH,
    reset_db: bool = True,
    run_consumer: bool = True,
) -> dict[str, Any]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if reset_db and db_path.exists():
        db_path.unlink()

    repository = SQLiteNewsRepository(db_path)
    source_runs: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    bad_payloads: list[dict[str, Any]] = []

    for source in build_ingestion_qa_sources():
        result = fetch_and_store_source(source, repository)
        invalid_payloads = int(getattr(source, "last_invalid_payload_count", 0))
        payload_seen = int(getattr(source, "last_payload_seen", result.seen))
        normalized_seen = int(result.seen)
        deduped = max(normalized_seen - int(result.inserted), 0)
        source_runs.append(
            {
                "source_name": result.source_name,
                "source_type": result.source_type,
                "payload_seen": payload_seen,
                "normalized_seen": normalized_seen,
                "inserted": int(result.inserted),
                "deduped": deduped,
                "invalid_payloads": invalid_payloads,
                "failed": result.failed,
                "error_message": result.error_message,
            }
        )
        if result.failed and result.error_message:
            failures.append(
                {
                    "source_name": result.source_name,
                    "error_message": result.error_message,
                }
            )
        for example in getattr(source, "last_invalid_payload_examples", []):
            bad_payloads.append(
                {
                    "source_name": result.source_name,
                    "reason": str(example["reason"]),
                    "payload": dict(example["payload"]),
                }
            )

    consumer_result = {"processed": 0, "analyzed": 0, "skipped": 0, "errors": 0}
    if run_consumer:
        consumer_result = consume_pending_news(
            repository=repository,
            sorter=NewsSorterAgent(),
            analyst=AnalystAgent(),
        )

    rows = repository.list_news_items(limit=50)
    resource_cards = [json.loads(row["resource_card_json"]) for row in rows if row.get("resource_card_json")]
    route_distribution = {"send_to_analysis": 0, "watchlist": 0, "archive_only": 0}
    for card in resource_cards:
        route = str(card.get("route_decision"))
        if route in route_distribution:
            route_distribution[route] += 1

    resource_card_count = len(resource_cards)
    average_analysis_readiness_score = None
    if resource_cards:
        average_analysis_readiness_score = round(
            sum(float(card["analysis_readiness_score"]) for card in resource_cards) / resource_card_count,
            4,
        )
    route_percentages = {
        route: round(count / resource_card_count, 4) if resource_card_count else 0.0
        for route, count in route_distribution.items()
    }
    source_distribution: dict[str, int] = {}
    for row in rows:
        source_name = str(row["source_name"])
        source_distribution[source_name] = source_distribution.get(source_name, 0) + 1

    status_counts = {
        "pending_sort": 0,
        "pending_analysis": 0,
        "analyzed": 0,
        "skipped": 0,
        "error": 0,
        **repository.get_status_counts(),
    }

    report = {
        "generated_at": now_iso(),
        "db_path": str(db_path),
        "report_path": str(report_path),
        "enabled_sources": [item["source_name"] for item in source_runs],
        "source_runs": source_runs,
        "totals": {
            "source_count": len(source_runs),
            "failed_sources": sum(1 for item in source_runs if item["failed"]),
            "payload_seen": sum(int(item["payload_seen"]) for item in source_runs),
            "normalized_seen": sum(int(item["normalized_seen"]) for item in source_runs),
            "inserted": sum(int(item["inserted"]) for item in source_runs),
            "deduped": sum(int(item["deduped"]) for item in source_runs),
            "invalid_payloads": sum(int(item["invalid_payloads"]) for item in source_runs),
        },
        "storage_metrics": {
            "news_items_total": len(rows),
            "new_items_this_run": sum(int(item["inserted"]) for item in source_runs),
            "source_distribution": source_distribution,
            "latest_titles": [f"{row['source_name']}: {row['title']}" for row in rows[:5]],
        },
        "cleaning_metrics": {
            "resource_card_count": resource_card_count,
            "average_analysis_readiness_score": average_analysis_readiness_score,
            "route_distribution": route_distribution,
            "route_percentages": route_percentages,
        },
        "status_counts": status_counts,
        "consumer_result": consumer_result,
        "samples": [
            {
                "news_item_id": int(row["id"]),
                "title": str(row["title"]),
                "source_name": str(row["source_name"]),
                "analysis_status": str(row["analysis_status"]),
                "raw_news": json.loads(row["raw_payload_json"]),
                "resource_card": json.loads(row["resource_card_json"]) if row.get("resource_card_json") else None,
            }
            for row in rows[:5]
        ],
        "failures": failures,
        "bad_payloads": bad_payloads,
    }
    write_json(report_path, report)
    return report


def render_ingestion_qa_report(report: dict[str, Any]) -> str:
    totals = report["totals"]
    route_distribution = report["cleaning_metrics"]["route_distribution"]
    return "\n".join(
        [
            "Ingestion QA Report",
            f"Generated at: {report['generated_at']}",
            f"Sources: {totals['source_count']} total / {totals['failed_sources']} failed",
            f"Payloads seen: {totals['payload_seen']}",
            f"Normalized items: {totals['normalized_seen']}",
            f"Inserted news items: {totals['inserted']}",
            f"Deduped items: {totals['deduped']}",
            f"Invalid payloads: {totals['invalid_payloads']}",
            (
                "Route distribution: "
                f"send_to_analysis={route_distribution['send_to_analysis']}, "
                f"watchlist={route_distribution['watchlist']}, "
                f"archive_only={route_distribution['archive_only']}"
            ),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ingestion QA fixture flow.")
    parser.add_argument("--db", default=str(DEFAULT_QA_DB_PATH), help="SQLite path for the QA run.")
    parser.add_argument("--report", default=str(DEFAULT_QA_REPORT_PATH), help="JSON report output path.")
    parser.add_argument("--skip-consumer", action="store_true", help="Only run ingest, do not consume pending news.")
    args = parser.parse_args()

    report = run_ingestion_qa(
        db_path=Path(args.db),
        report_path=Path(args.report),
        reset_db=True,
        run_consumer=not args.skip_consumer,
    )
    print(render_ingestion_qa_report(report))


if __name__ == "__main__":
    main()
