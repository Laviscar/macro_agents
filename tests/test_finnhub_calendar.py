import json

from sources.config import NewsSourceConfig
from sources.factory import build_source_adapter
from sources.finnhub_calendar import FinnhubEconCalendarAdapter

SAMPLE = json.dumps({"economicCalendar": [
    {"actual": 3.2, "country": "US", "estimate": 3.1, "event": "CPI YoY", "impact": "high", "prev": 3.0, "time": "2026-06-01 12:30:00", "unit": "%"},
    {"actual": None, "country": "US", "estimate": None, "event": "Fed Powell Speech", "impact": "medium", "prev": None, "time": "2026-06-02 14:00:00", "unit": ""},
    {"actual": 55.1, "country": "US", "estimate": 55.3, "event": "PMI", "impact": "low", "prev": 54.5, "time": "2026-06-01 13:45:00", "unit": ""},
    {"actual": 1.0, "country": "JP", "estimate": 0.9, "event": "GDP", "impact": "high", "prev": 0.8, "time": "2026-06-01 00:00:00", "unit": "%"},
]})


def _adapter(**kw):
    return FinnhubEconCalendarAdapter(source_name="econ", api_key="k", fetcher=lambda _u: SAMPLE, **kw)


def test_high_impact_only_filters_out_medium_low():
    items = _adapter(min_impact="high").fetch_latest()
    titles = " ".join(i.title for i in items)
    assert "CPI YoY" in titles and "GDP" in titles      # both high
    assert "Powell" not in titles and "PMI" not in titles  # medium/low dropped


def test_country_filter():
    items = _adapter(min_impact="high", countries=["US"]).fetch_latest()
    assert all("US" in i.title for i in items) and "JP" not in " ".join(i.title for i in items)


def test_actual_vs_upcoming_rendering():
    item = next(i for i in _adapter(min_impact="high").fetch_latest() if "CPI YoY" in i.title)
    assert "实际 3.2%" in item.title and "预期 3.1%" in item.title and "前值 3.0%" in item.title


def test_factory_builds_calendar_adapter():
    cfg = NewsSourceConfig(type="finnhub_econ_calendar", name="ec", api_key="k",
                           params={"min_impact": "high"})
    assert isinstance(build_source_adapter(cfg), FinnhubEconCalendarAdapter)
