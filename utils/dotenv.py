from __future__ import annotations

import os
from pathlib import Path

_EXPORT_PREFIX = "export "


def load_dotenv(path: str | Path = ".env", *, override: bool = False) -> dict[str, str]:
    """Load ``KEY=VALUE`` pairs from a .env file into ``os.environ``.

    Zero-dependency replacement for python-dotenv:
      - Blank lines and full-line ``#`` comments are ignored.
      - A leading ``export `` is stripped (so ``export FOO=bar`` works).
      - Surrounding single/double quotes around the value are removed.
      - A ``#`` inside a value is preserved (only full-line comments are dropped).
      - By default an existing environment variable is NOT overwritten, so an
        explicit shell ``export`` or real environment wins over the file.

    Returns the dict parsed from the file regardless of whether each key was
    written to ``os.environ`` (so callers can inspect what the file contained).
    Missing file is a no-op returning ``{}``.
    """
    file_path = Path(path)
    parsed: dict[str, str] = {}
    if not file_path.exists():
        return parsed

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(_EXPORT_PREFIX):
            line = line[len(_EXPORT_PREFIX):].lstrip()
        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        parsed[key] = value
        if override or key not in os.environ:
            os.environ[key] = value

    return parsed
