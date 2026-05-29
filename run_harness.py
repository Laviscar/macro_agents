from __future__ import annotations

import argparse
from pathlib import Path

from harness.coordinator import HarnessCoordinator
from repositories.news_repository import SQLiteNewsRepository

_DEFAULT_DB = "storage/macro_agents.sqlite3"
_DEFAULT_STORAGE = "storage"


def drain(
    db_path: str | Path,
    storage_root: str | Path = _DEFAULT_STORAGE,
    batch_size: int = 20,
    max_batches: int = 50,
    time_budget_seconds: float = 300.0,
) -> dict:
    """Repeatedly process pending news through the harness until drained or max_batches hit.

    Returns a summary dict: batches run, starting pending count, and final status counts.
    """
    repository = SQLiteNewsRepository(db_path)
    total_pending_start = len(repository.list_pending_news(limit=10_000))

    coordinator = HarnessCoordinator(db_path=db_path, storage_root=storage_root)

    batches = 0
    while batches < max_batches:
        if not repository.list_pending_news(limit=1):
            break
        coordinator.run_pending(limit=batch_size, time_budget_seconds=time_budget_seconds)
        batches += 1

    return {
        "batches": batches,
        "total_pending_start": total_pending_start,
        "status_counts": repository.get_status_counts(),
        "pending_remaining": len(repository.list_pending_news(limit=10_000)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Drain pending news through the Harness")
    parser.add_argument("--db", default=_DEFAULT_DB, help="Path to the news SQLite DB")
    parser.add_argument("--storage-root", default=_DEFAULT_STORAGE, help="Narrative storage root")
    parser.add_argument("--batch-size", type=int, default=20, help="News items per batch")
    parser.add_argument("--max-batches", type=int, default=50, help="Safety cap on batches")
    parser.add_argument("--time-budget", type=float, default=300.0, help="Per-batch time budget (s)")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    summary = drain(
        db_path=args.db,
        storage_root=args.storage_root,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        time_budget_seconds=args.time_budget,
    )
    print("Harness drain complete:")
    print(f"  batches run:          {summary['batches']}")
    print(f"  pending at start:     {summary['total_pending_start']}")
    print(f"  pending remaining:    {summary['pending_remaining']}")
    print(f"  status counts:        {summary['status_counts']}")


if __name__ == "__main__":
    main()
