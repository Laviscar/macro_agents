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

    def run_once(self) -> None:
        """Run every stage once, ignoring intervals (for manual/test runs)."""
        for stage in self.stages:
            try:
                stage.run_fn()
            except Exception as exc:
                log_event(self._logger, "stage_failed", stage=stage.name, error=str(exc))

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
