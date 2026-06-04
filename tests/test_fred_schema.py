from schemas.fred import FredReading


def test_reading_roundtrip():
    r = FredReading(series_id="DFII10", label="10Y实际利率", unit="%", node_id="实际利率",
                    value=1.93, date="2026-06-03", prev=1.89, change=0.04, fetched_at="t")
    again = FredReading.model_validate_json(r.model_dump_json())
    assert again.node_id == "实际利率" and again.change == 0.04


def test_general_reading_no_node():
    r = FredReading(series_id="UNRATE", label="失业率", unit="%", value=4.3, date="2026-06-01", fetched_at="t")
    assert r.node_id is None and r.prev is None
