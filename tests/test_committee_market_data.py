from committee.market_data import fetch_market_snapshot


def test_snapshot_formats_quote():
    q = {"c": 225.52, "d": 1.16, "dp": 0.517, "h": 232.28, "l": 224.72, "pc": 224.36}
    snap = fetch_market_snapshot("NVDA", fetcher=lambda sym: q)
    assert "NVDA" in snap and "现价 225.52" in snap and "+0.52%" in snap and "232.28/224.72" in snap


def test_unknown_asset_returns_none():
    assert fetch_market_snapshot("US10Y", fetcher=lambda sym: {"c": 0}) is None  # no proxy


def test_zero_price_returns_none():
    assert fetch_market_snapshot("NVDA", fetcher=lambda sym: {"c": 0}) is None   # finnhub unknown


def test_fetch_error_returns_none():
    def boom(sym):
        raise RuntimeError("net")
    assert fetch_market_snapshot("NVDA", fetcher=boom) is None
