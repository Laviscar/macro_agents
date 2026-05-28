import json

from sources.config import NewsSourceConfig
from sources.finnhub import FinnhubNewsAdapter


def test_finnhub_adapter_normalizes_general_news_payload() -> None:
    payload = json.dumps(
        [
            {
                "category": "general",
                "datetime": 1774742400,
                "headline": "Treasury yields slip after softer inflation print",
                "id": 10452,
                "image": "https://example.com/image.jpg",
                "related": "US10Y",
                "source": "Reuters",
                "summary": "Bond yields fell after CPI surprised to the downside.",
                "url": "https://example.com/finnhub-story",
            }
        ]
    )
    config = NewsSourceConfig(
        type="finnhub",
        name="finnhub_general",
        endpoint="https://finnhub.io/api/v1/news",
        api_key="demo-token",
        category="general",
        limit=20,
    )
    adapter = FinnhubNewsAdapter.from_config(
        config,
        fetcher=lambda _url: payload,
    )

    items = adapter.fetch_latest()

    assert len(items) == 1
    item = items[0]
    assert item.source_type == "finnhub"
    assert item.source_name == "finnhub_general"
    assert item.external_id == "10452"
    assert item.title == "Treasury yields slip after softer inflation print"
    assert item.summary == "Bond yields fell after CPI surprised to the downside."
    assert item.url == "https://example.com/finnhub-story"
    assert item.published_at == "2026-03-29T00:00:00+00:00"
    assert item.raw_payload["source"] == "finnhub_general"
    assert item.raw_payload["publisher"] == "Reuters"
    assert item.raw_payload["theme"] == ["inflation"]


def test_finnhub_adapter_builds_company_news_requests_from_symbols() -> None:
    requested_urls: list[str] = []
    config = NewsSourceConfig(
        type="finnhub",
        name="finnhub_symbols",
        endpoint="https://finnhub.io/api/v1/company-news",
        api_key="demo-token",
        symbols=["AAPL", "MSFT"],
        limit=5,
        lookback_days=3,
    )
    adapter = FinnhubNewsAdapter.from_config(
        config,
        fetcher=lambda url: requested_urls.append(url) or "[]",
    )

    adapter.fetch_latest()

    assert len(requested_urls) == 2
    assert "symbol=AAPL" in requested_urls[0]
    assert "symbol=MSFT" in requested_urls[1]
    assert "token=demo-token" in requested_urls[0]


def test_finnhub_adapter_skips_malformed_articles_without_failing_batch() -> None:
    payload = json.dumps(
        [
            {
                "category": "general",
                "datetime": 1774742400,
                "headline": "Treasury yields slip after softer inflation print",
                "id": 10452,
                "source": "Reuters",
                "summary": "Bond yields fell after CPI surprised to the downside.",
                "url": "https://example.com/finnhub-story",
            },
            {
                "category": "general",
                "datetime": 1774742401,
                "headline": "",
                "id": 10453,
                "source": "Reuters",
                "summary": "Malformed item with no headline.",
                "url": "https://example.com/bad-story",
            },
        ]
    )
    config = NewsSourceConfig(
        type="finnhub",
        name="finnhub_general",
        endpoint="https://finnhub.io/api/v1/news",
        api_key="demo-token",
    )
    adapter = FinnhubNewsAdapter.from_config(
        config,
        fetcher=lambda _url: payload,
    )

    items = adapter.fetch_latest()

    assert len(items) == 1
    assert items[0].external_id == "10452"
