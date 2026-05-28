from __future__ import annotations

import argparse
import logging
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable, Iterable, Mapping

from repositories.news_repository import SQLiteNewsRepository
from sources.base import NewsSource
from sources.config import NewsServiceConfig, RetryConfig, load_news_service_config, resolve_news_service_config_path
from sources.factory import build_source_adapter
from sources.rss_feed import RssFeedAdapter
from utils.logger import get_logger, log_event

APP_ROOT = Path(__file__).resolve().parent.parent


def fetch_and_store_feed(
    adapter: RssFeedAdapter,
    repository: SQLiteNewsRepository,
) -> dict[str, int]:
    result = fetch_and_store_source(adapter, repository)
    return {
        "seen": result.seen,
        "inserted": result.inserted,
    }


def poll_feed_forever(
    adapter: RssFeedAdapter,
    repository: SQLiteNewsRepository,
    interval_seconds: int = 300,
) -> None:
    service = PollingIngestService(
        sources=[{"adapter": adapter, "interval_seconds": interval_seconds}],
        repository=repository,
    )
    service.serve_forever()


@dataclass(eq=True)
class SourcePollResult:
    source_name: str
    source_type: str
    seen: int
    inserted: int
    failed: bool
    error_message: str | None = None


@dataclass
class PollingSourceState:
    adapter: NewsSource
    interval_seconds: int
    next_run_at: float = 0.0


def fetch_and_store_source(
    source: NewsSource,
    repository: SQLiteNewsRepository,
    retry_config: RetryConfig | None = None,
    logger: logging.Logger | None = None,
    sleep_func: Callable[[float], None] = time.sleep,
) -> SourcePollResult:
    retry = retry_config or RetryConfig()
    source_name = getattr(source, "source_name", source.__class__.__name__)
    source_type = getattr(source, "source_type", "unknown")
    attempt = 0

    while attempt < retry.max_attempts:
        attempt += 1
        try:
            items = source.fetch_latest()
            before = repository.count_news_items()
            for item in items:
                repository.insert_news_item(item)
            after = repository.count_news_items()
            result = SourcePollResult(
                source_name=source_name,
                source_type=source_type,
                seen=len(items),
                inserted=after - before,
                failed=False,
                error_message=None,
            )
            if logger:
                log_event(
                    logger,
                    "source_poll_succeeded",
                    source_name=source_name,
                    source_type=source_type,
                    seen=result.seen,
                    inserted=result.inserted,
                    attempts=attempt,
                )
            return result
        except Exception as exc:
            if logger:
                log_event(
                    logger,
                    "source_poll_failed_attempt",
                    source_name=source_name,
                    source_type=source_type,
                    attempt=attempt,
                    max_attempts=retry.max_attempts,
                    error=str(exc),
                )
            if attempt >= retry.max_attempts:
                if logger:
                    log_event(
                        logger,
                        "source_poll_failed",
                        source_name=source_name,
                        source_type=source_type,
                        attempts=attempt,
                        error=str(exc),
                    )
                return SourcePollResult(
                    source_name=source_name,
                    source_type=source_type,
                    seen=0,
                    inserted=0,
                    failed=True,
                    error_message=str(exc),
                )
            backoff_seconds = min(
                retry.backoff_seconds * (2 ** (attempt - 1)),
                retry.max_backoff_seconds,
            )
            sleep_func(backoff_seconds)


class PollingIngestService:
    def __init__(
        self,
        *,
        sources: Iterable[PollingSourceState | Mapping[str, object]],
        repository: SQLiteNewsRepository,
        retry_config: RetryConfig | None = None,
        logger: logging.Logger | None = None,
        idle_sleep_seconds: float = 1.0,
        monotonic=time.monotonic,
    ) -> None:
        self.repository = repository
        self.retry_config = retry_config or RetryConfig()
        self.logger = logger or get_logger("macro_agents.live_ingest")
        self.idle_sleep_seconds = idle_sleep_seconds
        self.monotonic = monotonic
        self._stop_event = Event()
        self._sources = [self._coerce_source_state(source) for source in sources]

    @property
    def stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def stop(self) -> None:
        self._stop_event.set()

    def build_signal_handler(self):
        def _handle_signal(signum: int, _frame: object) -> None:
            try:
                signal_name = signal.Signals(signum).name
            except ValueError:
                signal_name = str(signum)
            log_event(self.logger, "service_stop_requested", signal=signal_name)
            self.stop()

        return _handle_signal

    def install_signal_handlers(self) -> None:
        handler = self.build_signal_handler()
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def run_once(self, now_monotonic: float | None = None) -> list[SourcePollResult]:
        now_value = self.monotonic() if now_monotonic is None else now_monotonic
        results: list[SourcePollResult] = []
        for source_state in self._sources:
            if source_state.next_run_at > now_value:
                continue
            result = fetch_and_store_source(
                source_state.adapter,
                self.repository,
                retry_config=self.retry_config,
                logger=self.logger,
            )
            results.append(result)
            source_state.next_run_at = now_value + source_state.interval_seconds
        return results

    def serve_forever(self) -> None:
        self.install_signal_handlers()
        log_event(self.logger, "service_started", source_count=len(self._sources))
        while not self.stop_requested:
            self.run_once()
            if self.stop_requested:
                break
            sleep_seconds = self._sleep_until_next_due()
            self._stop_event.wait(timeout=sleep_seconds)
        log_event(self.logger, "service_stopped")

    def _sleep_until_next_due(self) -> float:
        if not self._sources:
            return self.idle_sleep_seconds
        now_value = self.monotonic()
        nearest_due = min(source.next_run_at for source in self._sources)
        if nearest_due <= now_value:
            return 0.0
        return min(nearest_due - now_value, self.idle_sleep_seconds)

    def _coerce_source_state(self, source: PollingSourceState | Mapping[str, object]) -> PollingSourceState:
        if isinstance(source, PollingSourceState):
            return source
        adapter = source["adapter"]
        interval_seconds = int(source["interval_seconds"])
        return PollingSourceState(adapter=adapter, interval_seconds=interval_seconds)


def build_polling_service(
    config: NewsServiceConfig,
    repository: SQLiteNewsRepository,
    logger: logging.Logger | None = None,
) -> PollingIngestService:
    sources = [
        {
            "adapter": build_source_adapter(source_config),
            "interval_seconds": source_config.resolved_poll_interval_seconds(
                config.service.default_poll_interval_seconds
            ),
        }
        for source_config in config.enabled_sources()
    ]
    return PollingIngestService(
        sources=sources,
        repository=repository,
        retry_config=config.service.retry,
        logger=logger,
        idle_sleep_seconds=config.service.idle_sleep_seconds,
    )


def resolve_db_path(config_path: Path, db_path_value: str) -> Path:
    db_path = Path(db_path_value)
    if db_path.is_absolute():
        return db_path
    return (config_path.parent / db_path).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Macro Agents live ingest service.")
    parser.add_argument(
        "--config",
        default="config/sources.yaml",
        help="Path to the news source config YAML.",
    )
    args = parser.parse_args()
    config_path = resolve_news_service_config_path(Path(APP_ROOT / args.config) if not Path(args.config).is_absolute() else Path(args.config))
    config_path = config_path.resolve()
    config = load_news_service_config(config_path)
    repository = SQLiteNewsRepository(resolve_db_path(config_path, config.service.db_path))
    service = build_polling_service(config, repository)
    service.serve_forever()


if __name__ == "__main__":
    main()
