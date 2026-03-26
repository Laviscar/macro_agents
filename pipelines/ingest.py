from __future__ import annotations

import json
from pathlib import Path


def load_raw_news(path: str) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_manual_md(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")
