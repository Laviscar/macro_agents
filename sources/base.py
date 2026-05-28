from __future__ import annotations

from typing import Protocol, runtime_checkable

from schemas.raw_news_item import RawNewsItem


@runtime_checkable
class NewsSource(Protocol):
    source_name: str
    source_type: str

    def fetch_latest(self) -> list[RawNewsItem]:
        ...
