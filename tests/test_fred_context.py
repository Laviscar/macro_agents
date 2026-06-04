from committee.fred_context import fred_context_block
from repositories.fred_repository import FredRepository
from schemas.fred import FredReading


def _r(sid, node, val, ch):
    return FredReading(series_id=sid, label=("失业率" if node is None else "10Y实际利率"),
                       unit="%", node_id=node, value=val, date="2026-06-03", change=ch, fetched_at="t")


def test_block_lists_driver_and_general(tmp_path):
    repo = FredRepository(tmp_path)
    repo.save_reading(_r("DFII10", "实际利率", 1.93, 0.04))
    repo.save_reading(_r("UNRATE", None, 4.3, None))
    block = fred_context_block(repo, driver_node_ids=["实际利率", "央行购金"])
    assert "10Y实际利率 1.93%" in block and "+0.04" in block
    assert "失业率 4.3%" in block
    assert "央行购金" not in block      # no FRED reading -> skipped


def test_empty_repo_returns_empty(tmp_path):
    assert fred_context_block(FredRepository(tmp_path), driver_node_ids=["实际利率"]) == ""
