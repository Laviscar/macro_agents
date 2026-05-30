from __future__ import annotations

import json
import urllib.request
from typing import Callable

# transport(url, headers, body_bytes, timeout) -> parsed json dict
TransportFn = Callable[[str, dict, bytes, float], dict]


def urllib_transport(url: str, headers: dict, body: bytes, timeout: float) -> dict:
    """Default HTTP transport: POST JSON via stdlib urllib and parse the JSON response."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted config URL)
        return json.loads(resp.read().decode("utf-8"))
