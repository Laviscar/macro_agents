import json
from sources.fred import FredClient, FredError


def _resp(obs):
    return json.dumps({"observations": obs})


def test_latest_and_prev_and_change():
    fc = FredClient(api_key="k", fetcher=lambda url: _resp([
        {"date": "2026-06-03", "value": "1.93"}, {"date": "2026-06-02", "value": "1.89"}]))
    assert fc.fetch_observation("DFII10") == (1.93, "2026-06-03", 1.89)


def test_skips_missing_dots():
    fc = FredClient(api_key="k", fetcher=lambda url: _resp([
        {"date": "2026-06-03", "value": "."}, {"date": "2026-06-02", "value": "1.90"},
        {"date": "2026-06-01", "value": "1.85"}]))
    assert fc.fetch_observation("DFII10") == (1.90, "2026-06-02", 1.85)


def test_no_valid_raises():
    fc = FredClient(api_key="k", fetcher=lambda url: _resp([{"date": "d", "value": "."}]))
    try:
        fc.fetch_observation("X"); assert False
    except FredError:
        pass


def test_missing_key_raises():
    try:
        FredClient(api_key=None, api_key_env="NOPE_FRED_KEY_XYZ").fetch_observation("X"); assert False
    except FredError:
        pass
