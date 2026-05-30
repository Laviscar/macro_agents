from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RetryConfig(BaseModel):
    max_attempts: int = 2
    backoff_seconds: float = 2.0
    max_backoff_seconds: float = 30.0


class NewsServiceSettings(BaseModel):
    db_path: str = "storage/macro_agents.sqlite3"
    default_poll_interval_seconds: int = 300
    idle_sleep_seconds: float = 1.0
    retry: RetryConfig = Field(default_factory=RetryConfig)


class NewsSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    name: str
    enabled: bool = True
    poll_interval_seconds: int | None = None
    url: str | None = None
    endpoint: str | None = None
    api_key_env: str | None = None
    api_key: str | None = None
    symbols: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    region: str | None = None
    category: str | None = None
    limit: int | None = None
    lookback_days: int = 3
    params: dict[str, Any] = Field(default_factory=dict)

    def resolved_poll_interval_seconds(self, default_interval_seconds: int) -> int:
        return int(self.poll_interval_seconds or default_interval_seconds)

    def resolved_symbols(self) -> list[str]:
        merged = [*self.symbols, *self.tickers]
        seen: set[str] = set()
        unique: list[str] = []
        for symbol in merged:
            cleaned = symbol.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            unique.append(cleaned)
        return unique


class TrustedSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str
    category: str
    reliability_tier: str = "primary"
    url: str
    endpoints: list[str] = Field(default_factory=list)
    notes: str | None = None


class NewsServiceConfig(BaseModel):
    service: NewsServiceSettings = Field(default_factory=NewsServiceSettings)
    sources: list[NewsSourceConfig] = Field(default_factory=list)
    trusted_sources: list[TrustedSourceConfig] = Field(default_factory=list)

    def enabled_sources(self) -> list[NewsSourceConfig]:
        return [source for source in self.sources if source.enabled]


def load_news_service_config(path: str | Path) -> NewsServiceConfig:
    config_path = resolve_news_service_config_path(path)
    raw_text = config_path.read_text(encoding="utf-8")
    raw_data = yaml.safe_load(raw_text) or {}
    return NewsServiceConfig.model_validate(raw_data)


def resolve_news_service_config_path(path: str | Path) -> Path:
    requested_path = Path(path)
    if requested_path.exists():
        return requested_path

    compatibility_map = {
        Path("configs/feeds.yaml"): Path("config/sources.yaml"),
    }
    for legacy_suffix, new_suffix in compatibility_map.items():
        if requested_path.parts[-len(legacy_suffix.parts) :] != legacy_suffix.parts:
            continue
        compatibility_path = requested_path.parent.parent / new_suffix.parent.name / new_suffix.name
        if compatibility_path.exists():
            return compatibility_path

    return requested_path
