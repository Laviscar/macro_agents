from repositories.fred_repository import FredRepository
from schemas.fred import FredReading


def _r(sid, node, val):
    return FredReading(series_id=sid, label=sid, unit="%", node_id=node, value=val,
                       date="2026-06-03", fetched_at="t")


def test_save_list_and_lookup(tmp_path):
    repo = FredRepository(tmp_path)
    repo.save_reading(_r("DFII10", "实际利率", 1.93))
    repo.save_reading(_r("UNRATE", None, 4.3))
    assert {x.series_id for x in repo.list_readings()} == {"DFII10", "UNRATE"}
    assert repo.reading_for_node("实际利率").value == 1.93
    assert repo.reading_for_node("nope") is None
    assert [g.series_id for g in repo.general_readings()] == ["UNRATE"]
