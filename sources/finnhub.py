from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sources.config import NewsSourceConfig
from sources.normalization import build_raw_news_item


FetchText = Callable[[str], str]


class FinnhubNewsAdapter:
    source_type = "finnhub"

    def __init__(
        self,
        *,
        source_name: str,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = None,
        category: str | None = None,
        symbols: Iterable[str] | None = None,
        limit: int | None = None,
        lookback_days: int = 3,
        fetcher: FetchText | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.source_name = source_name
        self.endpoint = endpoint or "https://finnhub.io/api/v1/news"
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.category = category or "general"
        self.symbols = [symbol.strip() for symbol in (symbols or []) if symbol.strip()]
        self.limit = limit
        self.lookback_days = lookback_days
        self.fetcher = fetcher or self._default_fetcher
        self.logger = logger or logging.getLogger("macro_agents.sources.finnhub")

    @classmethod
    def from_config(
        cls,
        config: NewsSourceConfig,
        fetcher: FetchText | None = None,
    ) -> "FinnhubNewsAdapter":
        adapter = cls(
            source_name=config.name,
            endpoint=config.endpoint,
            api_key=config.api_key,
            api_key_env=config.api_key_env,
            category=config.category,
            symbols=config.resolved_symbols(),
            limit=config.limit,
            lookback_days=config.lookback_days,
            fetcher=fetcher,
        )
        adapter.validate_configuration()
        return adapter

    def fetch_latest(self) -> list:
        articles: list[dict] = []
        for request_url in self._build_request_urls():
            payload = self.fetcher(request_url)
            articles.extend(self._parse_payload(payload))

        normalized = []
        for article in articles:
            try:
                normalized.append(self._normalize_article(article))
            except ValueError as exc:
                self.logger.warning(
                    "Skipping malformed Finnhub article for source '%s': %s",
                    self.source_name,
                    exc,
                )
        deduped = self._dedupe_items(normalized)
        if self.limit is not None:
            return deduped[: self.limit]
        return deduped

    def _build_request_urls(self) -> list[str]:
        token = self._resolve_api_key()
        if self.symbols:
            return [self._build_company_news_url(symbol, token) for symbol in self.symbols]
        return [self._build_general_news_url(token)]

    def validate_configuration(self) -> None:
        self._resolve_api_key()

    def _build_general_news_url(self, token: str) -> str:
        query = urlencode(
            {
                "category": self.category,
                "token": token,
            }
        )
        return f"{self.endpoint}?{query}"

    def _build_company_news_url(self, symbol: str, token: str) -> str:
        today = datetime.now(timezone.utc).date()
        start_date = today - timedelta(days=self.lookback_days)
        query = urlencode(
            {
                "symbol": symbol,
                "from": start_date.isoformat(),
                "to": today.isoformat(),
                "token": token,
            }
        )
        return f"{self.endpoint}?{query}"

    def _parse_payload(self, payload: str) -> list[dict]:
        data = json.loads(payload)
        if not isinstance(data, list):
            raise ValueError("Finnhub response must be a list of news items.")
        return [item for item in data if isinstance(item, dict)]

    def _normalize_article(self, article: dict) -> object:
        headline = str(article.get("headline") or "").strip()
        url = str(article.get("url") or "").strip()
        if not headline or not url:
            raise ValueError("Finnhub article is missing required headline/url fields.")

        summary = str(article.get("summary") or headline).strip()
        article_id = article.get("id")
        published_at = self._normalize_timestamp(article.get("datetime"))
        extra_payload = {
            "publisher": article.get("source"),
            "category": article.get("category"),
            "image": article.get("image"),
            "related": article.get("related"),
            "finnhub": article,
        }
        return build_raw_news_item(
            source_type=self.source_type,
            source_name=self.source_name,
            external_id=str(article_id) if article_id is not None else url,
            url=url,
            title=headline,
            summary=summary,
            published_at=published_at,
            extra_payload=extra_payload,
        )

    def _dedupe_items(self, items: list) -> list:
        seen: set[str] = set()
        deduped: list = []
        for item in sorted(items, key=lambda current: current.published_at or current.fetched_at, reverse=True):
            dedupe_key = item.build_dedupe_key()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            deduped.append(item)
        return deduped

    def _resolve_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            value = os.environ.get(self.api_key_env)
            if value:
                return value
            raise ValueError(
                f"Finnhub source '{self.source_name}' requires env var '{self.api_key_env}' to be set."
            )
        raise ValueError(f"Finnhub source '{self.source_name}' requires api_key or api_key_env.")

    def _normalize_timestamp(self, raw_value: object) -> str | None:
        if raw_value in (None, ""):
            return None
        timestamp = float(raw_value)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

    def _default_fetcher(self, request_url: str) -> str:
        request = Request(request_url, headers={"User-Agent": "macro-agents/1.0"})
        with urlopen(request, timeout=15) as response:
            return response.read().decode("utf-8")
