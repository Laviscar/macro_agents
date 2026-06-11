from datetime import datetime, timezone
from pathlib import Path

from pipelines.freshness import freshness_summary
from repositories.committee_repository import CommitteeRepository
from repositories.fred_repository import FredRepository
from repositories.graph_repository import GraphRepository
from schemas.committee import PendingConvocation
from schemas.fred import FredReading

CONFIG = str(Path(__file__).resolve().parent.parent / "config")
NOW = "2026-06-11T12:00:00+00:00"


class FakeNews:
    def list_news_items(self, limit=1):
        return [{"published_at": "2026-06-11T11:30:00+00:00", "fetched_at": "x"}]
    def get_latest_analysis_created_at(self):
        return "2026-06-11T10:00:00+00:00"
    def get_status_counts(self):
        return {"pending_sort": 147, "pending_analysis": 72, "analyzed": 145}


def test_freshness_ages_and_backlog(tmp_path):
    g = GraphRepository(tmp_path, CONFIG); g.seed_if_empty()
    c = CommitteeRepository(tmp_path, CONFIG)
    c.save_pending(PendingConvocation(asset_id="GOLD", asset_name="黄金", trigger="proximity", level=0.6,
                  ratio=0.7, leader="实际利率", runner_up="央行购金", is_reversal=True,
                  created_at="2026-06-11T09:00:00+00:00"))
    f = FredRepository(tmp_path)
    f.save_reading(FredReading(series_id="DFII10", label="x", unit="%", node_id="实际利率",
                   value=2.11, date="2026-06-09", fetched_at="t"))
    out = freshness_summary(FakeNews(), g, c, f, now=NOW)
    assert out["latest_news_age_min"] == 30.0          # 11:30 -> 12:00
    assert out["latest_evidence_age_min"] == 120.0     # 10:00 -> 12:00
    assert out["oldest_active_pending_age_min"] == 180.0  # 09:00 -> 12:00
    assert out["pending_sort_backlog"] == 147 and out["pending_analysis_backlog"] == 72
    assert out["latest_fred_date"] == "2026-06-09" and out["active_pending_count"] == 1
