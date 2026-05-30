import json
import pytest
from harness.eval import EvalReport
from harness.eval_cli import build_parser, format_report


def test_build_parser_defaults():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.window_days == 7
    assert args.db == "storage/macro_agents.sqlite3"
    assert args.format == "text"


def test_build_parser_custom_args():
    parser = build_parser()
    args = parser.parse_args(["--window-days", "14", "--db", "/tmp/test.db", "--format", "json"])
    assert args.window_days == 14
    assert args.db == "/tmp/test.db"
    assert args.format == "json"


def test_format_report_json():
    report = EvalReport(
        run_id="eval-001",
        window_start="2026-05-01",
        window_end="2026-05-07",
        session_count=3,
        metrics={
            "narrative_stability": 0.9,
            "evidence_precision": 0.8,
            "challenge_hit_rate": 1.0,
            "latency_seconds": 1.5,
            "tokens_used": 0,
        },
    )
    output = format_report(report, fmt="json")
    data = json.loads(output)
    assert data["run_id"] == "eval-001"
    assert data["session_count"] == 3
    assert data["metrics"]["narrative_stability"] == 0.9


def test_format_report_text():
    report = EvalReport(
        run_id="eval-001",
        window_start="2026-05-01",
        window_end="2026-05-07",
        session_count=2,
        metrics={
            "narrative_stability": 1.0,
            "evidence_precision": 0.75,
            "challenge_hit_rate": 1.0,
            "latency_seconds": 2.1,
            "tokens_used": 50,
        },
    )
    output = format_report(report, fmt="text")
    assert "eval-001" in output
    assert "narrative_stability" in output
    assert "session_count" in output
