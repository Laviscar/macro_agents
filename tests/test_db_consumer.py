from pathlib import Path

from agents.analyst import AnalystAgent
from agents.news_sorter import NewsSorterAgent
from pipelines.db_consumer import consume_pending_news
from repositories.news_repository import SQLiteNewsRepository
from schemas.raw_news_item import RawNewsItem


def test_db_consumer_processes_pending_news_into_analysis_and_evidence(tmp_path: Path) -> None:
    repository = SQLiteNewsRepository(tmp_path / "macro.sqlite3")
    repository.insert_news_item(
        RawNewsItem(
            source_type="rss",
            source_name="example_rss",
            external_id="item-1",
            url="https://example.com/cpi-cools",
            title="US CPI cools in March",
            summary="Inflation data came in softer than expected.",
            published_at="2026-03-30T08:00:00+00:00",
            fetched_at="2026-03-30T08:05:00+00:00",
            raw_payload={
                "title": "US CPI cools in March",
                "summary": "Inflation data came in softer than expected.",
                "source": "example_rss",
                "url": "https://example.com/cpi-cools",
                "region": ["US"],
                "theme": ["inflation"],
                "importance_score": 0.9,
                "structural_score": 0.8,
                "verifiability_score": 0.9,
                "timestamp": "2026-03-30T08:00:00+00:00",
            },
        )
    )

    result = consume_pending_news(
        repository=repository,
        sorter=NewsSorterAgent(),
        analyst=AnalystAgent(),
    )

    assert result["processed"] == 1
    assert result["analyzed"] == 1
    assert repository.count_analysis_cards() == 1
    assert repository.count_evidence_records() == 1
    row = repository.list_news_items(limit=1)[0]
    assert row["analysis_status"] == "analyzed"
    assert row["resource_card_json"] is not None
