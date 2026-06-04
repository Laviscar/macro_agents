from __future__ import annotations

from pathlib import Path

from schemas.fred import FredReading


def _safe(series_id: str) -> str:
    return series_id.replace("/", "_").replace(":", "_")


class FredRepository:
    """FRED 硬读数库:storage/fred_readings/<series>.json。"""

    def __init__(self, storage_root: str | Path) -> None:
        self.dir = Path(storage_root) / "fred_readings"
        self.dir.mkdir(parents=True, exist_ok=True)

    def save_reading(self, reading: FredReading) -> None:
        (self.dir / f"{_safe(reading.series_id)}.json").write_text(
            reading.model_dump_json(), encoding="utf-8")

    def list_readings(self) -> list[FredReading]:
        return [FredReading.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(self.dir.glob("*.json"))]

    def reading_for_node(self, node_id: str) -> FredReading | None:
        return next((r for r in self.list_readings() if r.node_id == node_id), None)

    def general_readings(self) -> list[FredReading]:
        return [r for r in self.list_readings() if not r.node_id]
