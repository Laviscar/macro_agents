from __future__ import annotations

import json
import os
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FetchText = Callable[[str], str]


class FredError(Exception):
    """FRED 取数失败(网络/无 key/无有效观测),由 stage 捕获跳过。"""


class FredClient:
    def __init__(self, api_key: str | None = None, api_key_env: str = "FRED_API_KEY",
                 endpoint: str = "https://api.stlouisfed.org/fred/series/observations",
                 fetcher: FetchText | None = None) -> None:
        self.api_key = api_key
        self.api_key_env = api_key_env
        self.endpoint = endpoint
        self.fetcher = fetcher or self._default_fetcher

    def _resolve_key(self) -> str:
        key = self.api_key or os.environ.get(self.api_key_env)
        if not key:
            raise FredError(f"FRED API key missing (set {self.api_key_env})")
        return key

    def fetch_observation(self, series_id: str) -> tuple[float, str, float | None]:
        """返回 (最新有效值, 其日期, 次新有效值)。跳过缺测 '.'。无有效值 → FredError。"""
        query = urlencode({"series_id": series_id, "api_key": self._resolve_key(),
                           "file_type": "json", "sort_order": "desc", "limit": 10})
        try:
            payload = self.fetcher(f"{self.endpoint}?{query}")
            obs = json.loads(payload).get("observations", [])
        except FredError:
            raise
        except Exception as exc:
            raise FredError(f"FRED fetch failed for {series_id}: {exc}") from exc

        valid: list[tuple[float, str]] = []
        for o in obs:
            v = o.get("value")
            if v in (None, ".", ""):
                continue
            try:
                valid.append((float(v), o.get("date", "")))
            except ValueError:
                continue
            if len(valid) >= 2:
                break
        if not valid:
            raise FredError(f"FRED has no valid observation for {series_id}")
        value, date = valid[0]
        prev = valid[1][0] if len(valid) > 1 else None
        return value, date, prev

    def _default_fetcher(self, url: str) -> str:
        req = Request(url, headers={"User-Agent": "macro_agents-fred/1.0"})
        with urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
