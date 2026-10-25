"""Read settings from the environment or a git-ignored .env file.

Values are never printed or logged. Real environment variables win over .env.
"""

from __future__ import annotations

import os
from pathlib import Path

from auditor.dataset import REPO_ROOT


def load_dotenv(path: Path = REPO_ROOT / ".env") -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        values[key] = val
    return values


def setting(name: str, default: str | None = None, path: Path = REPO_ROOT / ".env") -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    return load_dotenv(path).get(name) or default
