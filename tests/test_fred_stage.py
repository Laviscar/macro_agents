from pipelines.stages import fetch_fred_readings
from repositories.fred_repository import FredRepository
from sources.fred import FredError


class FakeClient:
    def fetch_observation(self, sid):
        if sid == "BAD":
            raise FredError("no data")
        return (1.93, "2026-06-03", 1.89)


def test_stage_writes_readings_and_counts_errors(tmp_path):
    repo = FredRepository(tmp_path)
    cfg = [{"series_id": "DFII10", "label": "10Y实际利率", "unit": "%", "node_id": "实际利率"},
           {"series_id": "BAD", "label": "坏", "unit": "%"}]
    out = fetch_fred_readings(repo, FakeClient(), cfg)
    assert out["fred_ok"] == 1 and out["fred_errors"] == 1
    r = repo.reading_for_node("实际利率")
    assert r.value == 1.93 and r.change == 0.04
