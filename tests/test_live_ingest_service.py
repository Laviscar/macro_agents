from __future__ import annotations

from pathlib import Path

import pytest

from pipelines.live_ingest import build_polling_service
from pipelines.live_ingest import PollingIngestService, SourcePollResult, fetch_and_store_source, resolve_db_path
from repositories.news_repository import SQLiteNewsRepository
from sources.config import NewsServiceConfig, NewsServiceSettings, NewsSourceConfig
from schemas.raw_news_item import RawNewsItem


class StaticSource:
    def __init__(self, source_name: str, items: list[RawNewsItem]) -> None:
        self.source_name = source_name
        self.source_type = items[0].source_type if items else "rss"
        self._items = items

    def fetch_latest(self) -> list[RawNewsItem]:
        return list(self._items)


class FailingSource:
    def __init__(self, source_name: str, error_message: str) -> None:
        self.source_name = source_name
        self.source_type = "finnhub"
        self.error_message = error_message

    def fetch_latest(self) -> list[RawNewsItem]:
        raise RuntimeError(self.error_message)


def make_item(source_name: str, external_id: str, *, source_type: str = "rss") -> RawNewsItem:
    return RawNewsItem(
        source_type=source_type,
        source_name=source_name,
        external_id=external_id,
        url=f"https://example.com/{source_name}/{external_id}",
        title=f"{source_name} headline {external_id}",
        summary=f"{source_name} summary {external_id}",
        published_at="2026-03-30T08:00:00+00:00",
        fetched_at="2026-03-30T08:05:00+00:00",
        raw_payload={"id": external_id},
    )


def test_fetch_and_store_source_persists_new_items(tmp_path: Path) -> None:
    repository = SQLiteNewsRepository(tmp_path / "macro.sqlite3")
    source = StaticSource("fed_rss", [make_item("fed_rss", "item-1")])

    result = fetch_and_store_source(source, repository)

    assert result == SourcePollResult(
        source_name="fed_rss",
        source_type="rss",
        seen=1,
        inserted=1,
        failed=False,
        error_message=None,
    )
    assert repository.count_news_items() == 1


def test_fetch_and_store_source_deduplicates_existing_news(tmp_path: Path) -> None:
    repository = SQLiteNewsRepository(tmp_path / "macro.sqlite3")
    source = StaticSource("fed_rss", [make_item("fed_rss", "item-1")])

    first = fetch_and_store_source(source, repository)
    second = fetch_and_store_source(source, repository)

    assert first.inserted == 1
    assert second.inserted == 0
    assert repository.count_news_items() == 1


def test_polling_service_continues_when_one_source_fails(tmp_path: Path) -> None:
    repository = SQLiteNewsRepository(tmp_path / "macro.sqlite3")
    healthy = StaticSource("fed_rss", [make_item("fed_rss", "item-1")])
    failing = FailingSource("finnhub_general", "temporary upstream failure")
    service = PollingIngestService(
        sources=[
            {"adapter": healthy, "interval_seconds": 60},
            {"adapter": failing, "interval_seconds": 60},
        ],
        repository=repository,
    )

    results = service.run_once(now_monotonic=0.0)

    assert repository.count_news_items() == 1
    assert len(results) == 2
    assert any(not result.failed and result.source_name == "fed_rss" for result in results)
    assert any(result.failed and result.source_name == "finnhub_general" for result in results)


def test_polling_service_only_polls_sources_when_due(tmp_path: Path) -> None:
    repository = SQLiteNewsRepository(tmp_path / "macro.sqlite3")
    source = StaticSource("fed_rss", [make_item("fed_rss", "item-1")])
    service = PollingIngestService(
        sources=[{"adapter": source, "interval_seconds": 60}],
        repository=repository,
    )

    first = service.run_once(now_monotonic=0.0)
    second = service.run_once(now_monotonic=30.0)
    third = service.run_once(now_monotonic=61.0)

    assert len(first) == 1
    assert second == []
    assert len(third) == 1


def test_polling_service_signal_handler_requests_graceful_stop(tmp_path: Path) -> None:
    repository = SQLiteNewsRepository(tmp_path / "macro.sqlite3")
    service = PollingIngestService(sources=[], repository=repository)

    handler = service.build_signal_handler()
    handler(15, None)

    assert service.stop_requested is True


def test_build_polling_service_fails_fast_when_finnhub_env_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    repository = SQLiteNewsRepository(tmp_path / "macro.sqlite3")
    config = NewsServiceConfig(
        service=NewsServiceSettings(),
        sources=[
            NewsSourceConfig(
                type="finnhub",
                name="finnhub_general",
                endpoint="https://finnhub.io/api/v1/news",
                api_key_env="FINNHUB_API_KEY",
                enabled=True,
            )
        ],
    )

    with pytest.raises(ValueError, match="FINNHUB_API_KEY"):
        build_polling_service(config, repository)


def test_resolve_db_path_is_relative_to_config_file_directory(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "sources.yaml"
    config_path.parent.mkdir()
    config_path.write_text("sources: []", encoding="utf-8")

    resolved = resolve_db_path(config_path, "../storage/macro_agents.sqlite3")

    assert resolved == (tmp_path / "storage" / "macro_agents.sqlite3")
