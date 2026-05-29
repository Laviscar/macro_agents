from __future__ import annotations

import argparse
import json
from datetime import date, timedelta

from harness.eval import EvalReport, EvalScheduler
from harness.session_store import HarnessSessionStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run eval harness over a time window")
    parser.add_argument("--db", default="storage/harness.db", help="Path to harness SQLite DB")
    parser.add_argument("--window-days", type=int, default=7, help="Number of days to look back")
    parser.add_argument("--format", choices=["json", "text"], default="text", help="Output format")
    return parser


def format_report(report: EvalReport, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(
            {
                "run_id": report.run_id,
                "window_start": report.window_start,
                "window_end": report.window_end,
                "session_count": report.session_count,
                "metrics": report.metrics,
            },
            indent=2,
        )
    lines = [
        f"Eval Report: {report.run_id}",
        f"  Window:        {report.window_start} → {report.window_end}",
        f"  session_count: {report.session_count}",
        "  Metrics:",
    ]
    for k, v in report.metrics.items():
        lines.append(f"    {k}: {v}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=args.window_days)).isoformat()
    store = HarnessSessionStore(args.db)
    scheduler = EvalScheduler(store)
    report = scheduler.run_eval(window_start=start_date, window_end=end_date)
    print(format_report(report, fmt=args.format))


if __name__ == "__main__":
    main()
