from pathlib import Path

from repositories.news_repository import SQLiteNewsRepository
from schemas.raw_news_item import RawNewsItem


def make_raw_news_item() -> RawNewsItem:
    return RawNewsItem(
        source_type="rss",
        source_name="example_rss",
        external_id="item-1",
        url="https://example.com/cpi-cools",
        title="US CPI cools in March",
        summary="Inflation data came in softer than expected.",
        published_at="2026-03-30T08:00:00+00:00",
        fetched_at="2026-03-30T08:05:00+00:00",
        raw_payload={"id": "item-1"},
    )


def test_sqlite_news_repository_deduplicates_news_items(tmp_path: Path) -> None:
    repository = SQLiteNewsRepository(tmp_path / "macro.sqlite3")
    item = make_raw_news_item()

    first_id = repository.insert_news_item(item)
    second_id = repository.insert_news_item(item)

    assert first_id == second_id
    assert repository.count_news_items() == 1
    rows = repository.list_news_items(limit=10)
    assert rows[0]["analysis_status"] == "pending_sort"
