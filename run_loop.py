from __future__ import annotations

import argparse
import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Callable

from utils.logger import get_logger, log_event


@dataclass
class Stage:
    name: str
    interval_seconds: float
    run_fn: Callable[[], object]
    last_run: float | None = field(default=None)

    def is_due(self, now: float) -> bool:
        return self.last_run is None or (now - self.last_run) >= self.interval_seconds


class RunLoop:
    def __init__(self, stages: list[Stage], logger=None) -> None:
        self.stages = stages
        self._logger = logger or get_logger("macro_agents.run_loop")
        self._stop = Event()

    def tick(self, now: float) -> None:
        for stage in self.stages:
            if not stage.is_due(now):
                continue
            stage.last_run = now
            try:
                result = stage.run_fn()
                log_event(self._logger, "stage_ran", stage=stage.name, result=result)
            except Exception as exc:  # isolate; never crash the loop
                log_event(self._logger, "stage_failed", stage=stage.name, error=str(exc))

    def run_once(self) -> list[dict]:
        """Run every stage once, ignoring intervals (for manual/test runs).
        Returns a per-stage summary list."""
        results: list[dict] = []
        for stage in self.stages:
            try:
                result = stage.run_fn()
                results.append({"stage": stage.name, "ok": True, "result": result})
            except Exception as exc:
                log_event(self._logger, "stage_failed", stage=stage.name, error=str(exc))
                results.append({"stage": stage.name, "ok": False, "error": str(exc)})
        return results

    def stop(self) -> None:
        self._stop.set()

    def serve_forever(self, tick_seconds: float = 30.0) -> None:
        signal.signal(signal.SIGINT, lambda *_: self.stop())
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        log_event(self._logger, "run_loop_started", stages=[s.name for s in self.stages])
        while not self._stop.is_set():
            self.tick(now=time.monotonic())
            self._stop.wait(timeout=tick_seconds)
        log_event(self._logger, "run_loop_stopped")


def _interval(env_key: str, default: float) -> float:
    try:
        return float(os.environ.get(env_key) or default)
    except ValueError:
        return default


def build_run_loop(
    db_path: str | Path = "storage/macro_agents.sqlite3",
    storage_root: str | Path = "storage",
    config_path: str | Path = "config/sources.yaml",
) -> "RunLoop":
    from agents.analyst import AnalystAgent
    from agents.narrative_manager import NarrativeManagerAgent
    from agents.news_sorter import NewsSorterAgent
    from agents.triage import TriageAgent
    from llm.config import load_llm_config
    from llm.factory import build_llm_client
    from pipelines.live_ingest import build_polling_service, load_news_service_config, resolve_news_service_config_path
    from pipelines.stages import analyze_pending, consolidate, triage_pending
    from repositories.news_repository import SQLiteNewsRepository

    repository = SQLiteNewsRepository(db_path)
    storage_root = Path(storage_root)
    run_state_path = storage_root / "run_state.json"

    # Three independently-keyed LLM tiers (each falls back to bare LLM_* when unset).
    triage_client = build_llm_client(load_llm_config(tier="triage"))
    analysis_client = build_llm_client(load_llm_config(tier="analysis"))
    narrative_client = build_llm_client(load_llm_config(tier="narrative"))

    sorter = NewsSorterAgent()
    triage_agent = TriageAgent(primary_client=triage_client, fallback_client=analysis_client)
    analyst = AnalystAgent(llm_client=analysis_client)
    narrative_manager = NarrativeManagerAgent(llm_client=narrative_client)

    cfg_path = resolve_news_service_config_path(Path(config_path)).resolve()
    ingest_service = build_polling_service(load_news_service_config(cfg_path), repository)

    triage_batch = int(_interval("RUN_LOOP_TRIAGE_BATCH", 20))
    analysis_batch = int(_interval("RUN_LOOP_ANALYSIS_BATCH", 10))

    stages = [
        Stage("ingest", _interval("RUN_LOOP_INGEST_SECONDS", 300), ingest_service.run_once),
        Stage("triage", _interval("RUN_LOOP_TRIAGE_SECONDS", 900),
              lambda: triage_pending(repository, triage_agent, sorter, limit=triage_batch)),
        Stage("analysis", _interval("RUN_LOOP_ANALYSIS_SECONDS", 900),
              lambda: analyze_pending(repository, analyst, limit=analysis_batch)),
        Stage("consolidation", _interval("RUN_LOOP_CONSOLIDATION_SECONDS", 3600),
              lambda: consolidate(repository, narrative_manager, storage_root, run_state_path)),
    ]
    return RunLoop(stages)


def main(argv: list[str] | None = None) -> None:
    from utils.dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the continuous macro_agents loop.")
    parser.add_argument("--db", default="storage/macro_agents.sqlite3")
    parser.add_argument("--storage-root", default="storage")
    parser.add_argument("--config", default="config/sources.yaml")
    parser.add_argument("--once", action="store_true", help="Run each stage once and exit.")
    args = parser.parse_args(argv)
    loop = build_run_loop(db_path=args.db, storage_root=args.storage_root, config_path=args.config)
    if args.once:
        loop.run_once()
    else:
        loop.serve_forever(tick_seconds=_interval("RUN_LOOP_TICK_SECONDS", 30))


if __name__ == "__main__":
    main()
