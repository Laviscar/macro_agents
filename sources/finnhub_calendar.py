from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from dateutil.parser import parse as parse_datetime

from sources.config import NewsSourceConfig
from sources.normalization import build_raw_news_item

FetchText = Callable[[str], str]

_IMPACT_RANK = {"low": 1, "medium": 2, "high": 3}


class FinnhubEconCalendarAdapter:
    """Finnhub economic calendar → news-like items.

    Turns structured data-release events (CPI / FOMC / NFP / PMI…) into items the
    analyst can read into evidence about macro drivers (通胀预期 / 政策利率 / 增长预期…).
    Filtered to high-signal events (min_impact) and an optional country set so volume
    stays small. This is the BLS-equivalent: hard data releases, not just headlines.
    """

    source_type = "finnhub_econ_calendar"

    def __init__(
        self,
        *,
        source_name: str,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = None,
        min_impact: str = "high",
        countries: list[str] | None = None,
        lookback_days: int = 2,
        lookahead_days: int = 7,
        limit: int | None = None,
        fetcher: FetchText | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.source_name = source_name
        self.endpoint = endpoint or "https://finnhub.io/api/v1/calendar/economic"
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.min_impact = (min_impact or "high").lower()
        self.countries = {c.upper() for c in (countries or [])}  # empty = all
        self.lookback_days = lookback_days
        self.lookahead_days = lookahead_days
        self.limit = limit
        self.fetcher = fetcher or self._default_fetcher
        self.logger = logger or logging.getLogger("macro_agents.sources.finnhub_calendar")

    @classmethod
    def from_config(cls, config: NewsSourceConfig, fetcher: FetchText | None = None) -> "FinnhubEconCalendarAdapter":
        params = config.params or {}
        adapter = cls(
            source_name=config.name,
            endpoint=config.endpoint,
            api_key=config.api_key,
            api_key_env=config.api_key_env,
            min_impact=str(params.get("min_impact", "high")),
            countries=list(params.get("countries", [])),
            lookback_days=config.lookback_days,
            lookahead_days=int(params.get("lookahead_days", 7)),
            limit=config.limit,
            fetcher=fetcher,
        )
        adapter._resolve_api_key()  # fail fast if key missing
        return adapter

    def fetch_latest(self) -> list:
        events = self._parse_payload(self.fetcher(self._build_url()))
        items = []
        for event in events:
            if not self._keep(event):
                continue
            try:
                items.append(self._normalize_event(event))
            except (ValueError, KeyError) as exc:
                self.logger.warning("Skipping malformed calendar event for '%s': %s", self.source_name, exc)
        items.sort(key=lambda i: i.published_at or i.fetched_at, reverse=True)
        return items[: self.limit] if self.limit is not None else items

    def _keep(self, event: dict) -> bool:
        impact_ok = _IMPACT_RANK.get(str(event.get("impact", "")).lower(), 0) >= _IMPACT_RANK.get(self.min_impact, 3)
        country_ok = not self.countries or str(event.get("country", "")).upper() in self.countries
        return impact_ok and country_ok

    def _build_url(self) -> str:
        today = datetime.now(timezone.utc).date()
        query = urlencode({
            "from": (today - timedelta(days=self.lookback_days)).isoformat(),
            "to": (today + timedelta(days=self.lookahead_days)).isoformat(),
            "token": self._resolve_api_key(),
        })
        return f"{self.endpoint}?{query}"

    def _parse_payload(self, payload: str) -> list[dict]:
        data = json.loads(payload)
        events = data.get("economicCalendar") if isinstance(data, dict) else data
        if not isinstance(events, list):
            raise ValueError("Finnhub economic calendar response is malformed.")
        return [e for e in events if isinstance(e, dict)]

    def _normalize_event(self, event: dict) -> object:
        country = str(event.get("country", "")).strip()
        name = str(event.get("event", "")).strip()
        impact = str(event.get("impact", "")).strip()
        time_raw = str(event.get("time", "")).strip()
        if not name or not time_raw:
            raise ValueError("event missing name/time")
        unit = str(event.get("unit", "") or "")
        actual, estimate, prev = event.get("actual"), event.get("estimate"), event.get("prev")

        def _fmt(v):
            return f"{v}{unit}" if v is not None else "—"

        if actual is not None:
            detail = f"实际 {_fmt(actual)} / 预期 {_fmt(estimate)} / 前值 {_fmt(prev)}"
        else:
            detail = f"即将公布(预期 {_fmt(estimate)} / 前值 {_fmt(prev)})"
        title = f"[{country} · {impact}] {name}：{detail}"

        published_at = parse_datetime(time_raw).replace(tzinfo=timezone.utc).isoformat()
        external_id = f"{country}|{name}|{time_raw}"
        url = f"https://finnhub.io/calendar/economic#{quote(external_id)}"
        return build_raw_news_item(
            source_type=self.source_type,
            source_name=self.source_name,
            external_id=external_id,
            url=url,
            title=title,
            summary=title,
            published_at=published_at,
            extra_payload={"finnhub_event": event},
        )

    def _resolve_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            value = os.environ.get(self.api_key_env)
            if value:
                return value
        raise ValueError(f"Finnhub econ-calendar source '{self.source_name}' is missing an API key.")

    def _default_fetcher(self, url: str) -> str:
        with urlopen(url, timeout=15) as response:
            return response.read().decode("utf-8")
