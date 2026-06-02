from pathlib import Path

import pytest

from sources.config import load_news_service_config


def test_load_news_service_config_supports_multiple_sources(tmp_path: Path) -> None:
    config_path = tmp_path / "feeds.yaml"
    config_path.write_text(
        """
service:
  db_path: storage/macro_agents.sqlite3
  default_poll_interval_seconds: 180
  retry:
    max_attempts: 3
    backoff_seconds: 2
sources:
  - type: rss
    name: fed_rss
    url: https://example.com/fed.xml
  - type: finnhub
    name: finnhub_general
    enabled: false
    endpoint: https://finnhub.io/api/v1/news
    api_key_env: FINNHUB_API_KEY
    poll_interval_seconds: 60
    symbols:
      - AAPL
      - MSFT
    limit: 10
""".strip(),
        encoding="utf-8",
    )

    config = load_news_service_config(config_path)

    assert config.service.db_path == "storage/macro_agents.sqlite3"
    assert config.service.default_poll_interval_seconds == 180
    assert config.service.retry.max_attempts == 3
    assert config.service.retry.backoff_seconds == 2
    assert len(config.sources) == 2
    assert config.sources[0].type == "rss"
    assert config.sources[0].resolved_poll_interval_seconds(180) == 180
    assert config.sources[1].type == "finnhub"
    assert config.sources[1].symbols == ["AAPL", "MSFT"]
    assert config.enabled_sources() == [config.sources[0]]


def test_default_sources_config_enabled_set() -> None:
    config = load_news_service_config(Path("config/sources.yaml"))

    enabled = {source.name for source in config.enabled_sources()}

    assert enabled == {
        "finnhub_general", "finnhub_crypto", "finnhub_econ_calendar",
        "fed_rss", "ecb_blog", "nyt_economy", "bis_press_rss",
    }
    # bls (403-blocks programmatic access) and symbol-specific company news stay off
    assert {"bls_latest_rss", "finnhub_symbols"}.isdisjoint(enabled)


def test_default_sources_config_includes_trusted_source_catalog() -> None:
    config = load_news_service_config(Path("config/sources.yaml"))

    trusted_source_names = {source.name for source in config.trusted_sources}

    assert "federal_reserve" in trusted_source_names
    assert "bls" in trusted_source_names
    assert "imf" in trusted_source_names
    assert "reuters" in trusted_source_names
    assert all(source.reliability_tier == "primary" for source in config.trusted_sources[:10])


def test_load_news_service_config_supports_legacy_configs_feeds_path(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text(
        """
service:
  db_path: ../storage/macro_agents.sqlite3
sources:
  - type: finnhub
    name: finnhub_general
    endpoint: https://finnhub.io/api/v1/news
    api_key_env: FINNHUB_API_KEY
""".strip(),
        encoding="utf-8",
    )

    config = load_news_service_config(tmp_path / "configs" / "feeds.yaml")

    assert config.service.db_path == "../storage/macro_agents.sqlite3"
    assert [source.name for source in config.enabled_sources()] == ["finnhub_general"]


def test_load_news_service_config_rejects_unknown_top_level_source_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(
        """
sources:
  - type: rss
    name: fed_rss
    url: https://example.com/fed.xml
    poll_interva_seconds: 60
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="poll_interva_seconds"):
        load_news_service_config(config_path)


def test_load_news_service_config_accepts_params_for_source_specific_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(
        """
sources:
  - type: finnhub
    name: finnhub_general
    endpoint: https://finnhub.io/api/v1/news
    api_key_env: FINNHUB_API_KEY
    params:
      language: en
      sentiment_window: 7
""".strip(),
        encoding="utf-8",
    )

    config = load_news_service_config(config_path)

    assert config.sources[0].params == {"language": "en", "sentiment_window": 7}
