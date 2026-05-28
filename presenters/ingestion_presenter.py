from __future__ import annotations

from utils.io import read_json
from view_models.ingestion_qa import (
    IngestionCleaningSummary,
    IngestionFailureCard,
    IngestionQABadPayloadCard,
    IngestionQAOverview,
    IngestionRunSummary,
    IngestionSampleCard,
    IngestionSourceRunCard,
    IngestionStatusSummary,
)


def build_ingestion_qa_overview(report_path) -> IngestionQAOverview:
    report = read_json(report_path, default=None)
    if not report:
        return IngestionQAOverview(
            report_available=False,
            headline="还没有 ingestion QA 报告。",
            summary="先运行 `python -m pipelines.ingestion_qa`，再回来查看抓取、去重、清洗和异常效果。",
            generated_at=None,
            run_summary=IngestionRunSummary(0, 0, 0, 0, 0, 0, 0, []),
            status_summary=IngestionStatusSummary(0, 0, 0, 0, 0),
            cleaning_summary=IngestionCleaningSummary(0, None, {}, {}, {}, []),
            source_runs=[],
            samples=[],
            failures=[],
            bad_payloads=[],
        )

    totals = report["totals"]
    status_counts = report["status_counts"]
    cleaning = report["cleaning_metrics"]
    storage_metrics = report["storage_metrics"]

    run_summary = IngestionRunSummary(
        source_count=int(totals["source_count"]),
        failed_source_count=int(totals["failed_sources"]),
        payload_seen_count=int(totals["payload_seen"]),
        normalized_seen_count=int(totals["normalized_seen"]),
        inserted_count=int(totals["inserted"]),
        deduped_count=int(totals["deduped"]),
        invalid_payload_count=int(totals["invalid_payloads"]),
        enabled_sources=list(report.get("enabled_sources", [])),
    )
    overview = IngestionQAOverview(
        report_available=True,
        headline=_build_headline(run_summary),
        summary=_build_summary(cleaning["route_distribution"], status_counts),
        generated_at=report.get("generated_at"),
        run_summary=run_summary,
        status_summary=IngestionStatusSummary(
            pending_sort_count=int(status_counts.get("pending_sort", 0)),
            pending_analysis_count=int(status_counts.get("pending_analysis", 0)),
            analyzed_count=int(status_counts.get("analyzed", 0)),
            skipped_count=int(status_counts.get("skipped", 0)),
            error_count=int(status_counts.get("error", 0)),
        ),
        cleaning_summary=IngestionCleaningSummary(
            resource_card_count=int(cleaning["resource_card_count"]),
            average_analysis_readiness_score=cleaning.get("average_analysis_readiness_score"),
            route_distribution={str(key): int(value) for key, value in cleaning["route_distribution"].items()},
            route_percentages={str(key): float(value) for key, value in cleaning["route_percentages"].items()},
            source_distribution={str(key): int(value) for key, value in storage_metrics["source_distribution"].items()},
            latest_titles=list(storage_metrics["latest_titles"]),
        ),
        source_runs=[
            IngestionSourceRunCard(
                source_name=str(item["source_name"]),
                source_type=str(item["source_type"]),
                payload_seen_count=int(item["payload_seen"]),
                normalized_seen_count=int(item["normalized_seen"]),
                inserted_count=int(item["inserted"]),
                deduped_count=int(item["deduped"]),
                invalid_payload_count=int(item["invalid_payloads"]),
                failed=bool(item["failed"]),
                error_message=item.get("error_message"),
            )
            for item in report["source_runs"]
        ],
        samples=[
            IngestionSampleCard(
                news_item_id=int(item["news_item_id"]),
                title=str(item["title"]),
                source_name=str(item["source_name"]),
                analysis_status=str(item["analysis_status"]),
                raw_news=dict(item["raw_news"]),
                resource_card=dict(item["resource_card"]) if item.get("resource_card") else None,
            )
            for item in report["samples"]
        ],
        failures=[
            IngestionFailureCard(
                source_name=str(item["source_name"]),
                error_message=str(item["error_message"]),
            )
            for item in report["failures"]
        ],
        bad_payloads=[
            IngestionQABadPayloadCard(
                source_name=str(item["source_name"]),
                reason=str(item["reason"]),
                payload=dict(item["payload"]),
            )
            for item in report["bad_payloads"]
        ],
    )
    return overview


def _build_headline(summary: IngestionRunSummary) -> str:
    return (
        f"这轮 QA 共跑了 {summary.source_count} 个 source，抓到 {summary.payload_seen_count} 条原始 payload，"
        f"成功标准化 {summary.normalized_seen_count} 条，入库 {summary.inserted_count} 条。"
    )


def _build_summary(route_distribution: dict, status_counts: dict) -> str:
    return (
        f"清洗路由：send_to_analysis={route_distribution.get('send_to_analysis', 0)}，"
        f"watchlist={route_distribution.get('watchlist', 0)}，archive_only={route_distribution.get('archive_only', 0)}。"
        f" 当前状态：analyzed={status_counts.get('analyzed', 0)}，skipped={status_counts.get('skipped', 0)}，"
        f"error={status_counts.get('error', 0)}。"
    )
