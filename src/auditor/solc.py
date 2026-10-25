"""Fetch pinned solc compiler binaries (Linux x86-64) and verify their sha256.

Binaries come from the official ethereum/solidity GitHub releases
(asset `solc-static-linux`) and are cached in .cache/solc/. A binary whose hash
does not match the pin below is deleted and an error is raised.
"""

from __future__ import annotations

import hashlib
import json
import stat
import urllib.request
from pathlib import Path

from auditor.dataset import REPO_ROOT

SOLC_DIR = REPO_ROOT / ".cache" / "solc"
GITHUB_URL = "https://github.com/ethereum/solidity/releases/download/v{v}/solc-static-linux"
OFFICIAL_LIST = "https://binaries.soliditylang.org/linux-amd64/list.json"

# sha256 of the GitHub release asset `solc-static-linux` for each version used by the dataset.
PINNED_SHA256 = {
    "0.4.24": "665675b9e0431c2572d59d6a7112afbdc752732ea0ce9aecf1a1855f28e02a09",
    "0.4.25": "c9b268750506b88fe71371100050e9dd1e7edcf8f69da34d1cd09557ecb24580",
    "0.4.26": "9f9da5a12fca278d75165f4ca75ee9d290d9f0bd8cabd59f16bf39cf0ac62192",
    "0.5.17": "c35ce7a4d3ffa5747c178b1e24c8541b2e5d8a82c1db3719eb4433a1f19e16f3",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def solc_path(version: str) -> Path:
    """Path to a verified solc binary for `version`, downloading it if needed."""
    if version not in PINNED_SHA256:
        raise ValueError(f"solc {version} is not pinned; add its sha256 to PINNED_SHA256")
    path = SOLC_DIR / f"solc-{version}"
    if path.exists() and _sha256(path) == PINNED_SHA256[version]:
        return path
    SOLC_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    print(f"downloading solc {version} from GitHub releases", flush=True)
    urllib.request.urlretrieve(GITHUB_URL.format(v=version), tmp)
    got = _sha256(tmp)
    if got != PINNED_SHA256[version]:
        tmp.unlink()
        raise RuntimeError(f"solc {version}: sha256 {got} does not match the pinned value")
    tmp.replace(path)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def compare_with_official_list() -> dict[str, str]:
    """Informational: does each pinned hash appear in soliditylang.org's list.json?"""
    try:
        with urllib.request.urlopen(OFFICIAL_LIST, timeout=20) as r:
            builds = json.load(r)["builds"]
    except Exception as exc:  # network or format problem: report, do not fail
        return {v: f"official list unavailable ({type(exc).__name__})" for v in PINNED_SHA256}
    official = {b["version"]: b.get("sha256", "").removeprefix("0x") for b in builds}
    return {
        v: ("matches" if official.get(v) == pin else f"differs (official {official.get(v) or 'missing'})")
        for v, pin in PINNED_SHA256.items()
    }


if __name__ == "__main__":
    for v in PINNED_SHA256:
        print(v, solc_path(v))
    print(json.dumps(compare_with_official_list(), indent=2))
