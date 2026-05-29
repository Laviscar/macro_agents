import pytest
from repositories.news_repository import SQLiteNewsRepository
from schemas.raw_news_item import RawNewsItem
from utils.clock import now_iso
from run_harness import drain


def _make_item(title: str) -> RawNewsItem:
    return RawNewsItem(
        source_type="rss",
        source_name="test",
        external_id=title,
        url=f"https://example.com/{title}",
        title=title,
        summary="test summary about inflation data",
        published_at=now_iso(),
        fetched_at=now_iso(),
        raw_payload={},
    )


def test_drain_processes_all_pending(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    repo = SQLiteNewsRepository(db_path)
    for title in ["GDP beats expectations", "Inflation cools sharply", "Trade gap widens"]:
        repo.insert_news_item(_make_item(title))

    summary = drain(
        db_path=db_path,
        storage_root=tmp_path / "storage",
        batch_size=2,
        max_batches=10,
    )

    assert summary["batches"] >= 1
    assert summary["total_pending_start"] == 3
    assert repo.list_pending_news(limit=10) == []


def test_drain_no_pending_runs_zero_batches(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    SQLiteNewsRepository(db_path)  # init empty DB
    summary = drain(
        db_path=db_path,
        storage_root=tmp_path / "storage",
        batch_size=5,
        max_batches=10,
    )
    assert summary["batches"] == 0
    assert summary["total_pending_start"] == 0


def test_drain_respects_max_batches(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    repo = SQLiteNewsRepository(db_path)
    for i in range(5):
        repo.insert_news_item(_make_item(f"Event number {i} about inflation"))

    summary = drain(
        db_path=db_path,
        storage_root=tmp_path / "storage",
        batch_size=1,
        max_batches=2,
    )
    assert summary["batches"] == 2
    # 5 inserted, batch_size 1, only 2 batches → 3 remain pending
    assert len(repo.list_pending_news(limit=10)) == 3
