from __future__ import annotations

from sources.base import NewsSource
from sources.config import NewsSourceConfig
from sources.finnhub import FinnhubNewsAdapter
from sources.finnhub_calendar import FinnhubEconCalendarAdapter
from sources.rss_feed import RssFeedAdapter


def build_source_adapter(config: NewsSourceConfig) -> NewsSource:
    source_type = config.type.lower().strip()
    if source_type == "rss":
        return RssFeedAdapter.from_config(config)
    if source_type == "finnhub":
        return FinnhubNewsAdapter.from_config(config)
    if source_type == "finnhub_econ_calendar":
        return FinnhubEconCalendarAdapter.from_config(config)
    raise ValueError(f"Unsupported source type: {config.type}")
