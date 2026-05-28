from __future__ import annotations

import json
from pathlib import Path

from pipelines.ingestion_qa import render_ingestion_qa_report, run_ingestion_qa
from presenters.ingestion_presenter import build_ingestion_qa_overview


def test_run_ingestion_qa_builds_report_and_persists_artifacts(tmp_path: Path) -> None:
    db_path = tmp_path / "storage" / "qa.sqlite3"
    report_path = tmp_path / "storage" / "ingestion_report.json"

    report = run_ingestion_qa(
        db_path=db_path,
        report_path=report_path,
        reset_db=True,
        run_consumer=True,
    )

    assert report["db_path"] == str(db_path)
    assert report["totals"]["payload_seen"] == 5
    assert report["totals"]["normalized_seen"] == 4
    assert report["totals"]["inserted"] == 3
    assert report["totals"]["deduped"] == 1
    assert report["totals"]["invalid_payloads"] == 1
    assert report["totals"]["failed_sources"] == 1
    assert report["storage_metrics"]["news_items_total"] == 3
    assert report["status_counts"]["analyzed"] == 1
    assert report["status_counts"]["skipped"] == 2
    assert report["cleaning_metrics"]["route_distribution"] == {
        "send_to_analysis": 1,
        "watchlist": 1,
        "archive_only": 1,
    }
    assert len(report["samples"]) == 3
    assert report["failures"][0]["source_name"] == "fixture_failing_source"
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["totals"]["inserted"] == 3


def test_render_ingestion_qa_report_contains_key_sections(tmp_path: Path) -> None:
    report = run_ingestion_qa(
        db_path=tmp_path / "qa.sqlite3",
        report_path=tmp_path / "ingestion_report.json",
        reset_db=True,
        run_consumer=True,
    )

    rendered = render_ingestion_qa_report(report)

    assert "Ingestion QA Report" in rendered
    assert "Sources: 2 total / 1 failed" in rendered
    assert "Payloads seen: 5" in rendered
    assert "Inserted news items: 3" in rendered
    assert "Route distribution: send_to_analysis=1, watchlist=1, archive_only=1" in rendered


def test_ingestion_presenter_builds_overview_from_report(tmp_path: Path) -> None:
    report_path = tmp_path / "storage" / "ingestion_report.json"
    run_ingestion_qa(
        db_path=tmp_path / "storage" / "qa.sqlite3",
        report_path=report_path,
        reset_db=True,
        run_consumer=True,
    )

    overview = build_ingestion_qa_overview(report_path)

    assert overview.report_available is True
    assert overview.run_summary.inserted_count == 3
    assert overview.run_summary.failed_source_count == 1
    assert overview.cleaning_summary.route_distribution["watchlist"] == 1
    assert overview.status_summary.analyzed_count == 1
    assert len(overview.samples) == 3
    assert overview.samples[0].raw_news["title"] != ""
    assert overview.samples[0].resource_card is not None
    assert len(overview.failures) == 1
    assert overview.failures[0].source_name == "fixture_failing_source"
