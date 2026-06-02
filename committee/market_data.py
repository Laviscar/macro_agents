from __future__ import annotations

import json
import os
from typing import Callable
from urllib.request import urlopen

FetchJson = Callable[[str], dict]

# 资产 → 一个 Finnhub 可免费报价的代理标的(美债收益率/中资股/部分汇率没有,留空即跳过)
_PROXY = {
    "SPX": "SPY", "NDX": "QQQ", "RUT": "IWM", "GOLD": "GLD", "COPPER": "CPER",
    "WTI": "USO", "BTC": "BINANCE:BTCUSDT", "MSCI_EM": "EEM", "NKY": "EWJ",
    # 主题股/ETF 用自身代码
    "NVDA": "NVDA", "SMH": "SMH", "MU": "MU", "VRT": "VRT", "ETN": "ETN", "SMCI": "SMCI",
    "CEG": "CEG", "VST": "VST", "URA": "URA", "XLE": "XLE",
    "XBI": "XBI", "LLY": "LLY", "JPM": "JPM", "KRE": "KRE", "COIN": "COIN",
}


def _default_fetcher(symbol: str) -> dict:
    token = os.environ.get("FINNHUB_API_KEY", "")
    with urlopen(f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={token}", timeout=12) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_market_snapshot(asset_id: str, fetcher: FetchJson | None = None) -> str | None:
    """该资产的二级市场量价快照文本,拿不到则 None。Finnhub /quote:c 现价 / dp %涨跌 / h,l 日高低。"""
    symbol = _PROXY.get(asset_id)
    if not symbol:
        return None
    fetcher = fetcher or _default_fetcher
    try:
        q = fetcher(symbol)
    except Exception:
        return None
    c = q.get("c")
    if not c:                       # Finnhub 对未知标的返回 c=0
        return None
    dp, h, l = q.get("dp"), q.get("h"), q.get("l")
    parts = [f"现价 {c}"]
    if dp is not None:
        parts.append(f"日内 {dp:+.2f}%")
    if h and l:
        parts.append(f"日高/低 {h}/{l}")
    return f"{symbol}: " + ",".join(parts)
