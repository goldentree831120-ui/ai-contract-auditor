"""Fetch a GitHub repository at a pinned commit into .cache/sources/ (idempotent)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from auditor.dataset import REPO_ROOT

CACHE = REPO_ROOT / ".cache" / "sources"


def fetch(repo: str, commit: str) -> Path:
    dest = CACHE / repo.replace("/", "__")
    if (dest / ".git" / "HEAD").exists():
        cur = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        if cur == commit:
            return dest
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    print(f"fetching {repo}@{commit[:10]}", flush=True)
    for cmd in (["git", "init", "-q"],
                ["git", "remote", "add", "origin", f"https://github.com/{repo}.git"],
                ["git", "fetch", "-q", "--depth", "1", "origin", commit],
                ["git", "checkout", "-q", "FETCH_HEAD"]):
        subprocess.run(cmd, cwd=dest, check=True)
    return dest
