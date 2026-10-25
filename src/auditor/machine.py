"""Describe the machine a result was produced on (recorded with every run)."""

from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _pkg(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def machine_info(packages: tuple[str, ...] = ()) -> dict:
    cpu = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    ram_gb = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                ram_gb = round(int(line.split()[1]) / 1024 / 1024, 1)
                break
    except OSError:
        pass
    kernel = platform.release()
    info = {
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "ram_gb_visible": ram_gb,
        "os": f"{platform.system()} {kernel}" + (" (WSL)" if "microsoft" in kernel.lower() else ""),
        "python": platform.python_version(),
    }
    for p in packages:
        info[p.replace("-", "_")] = _pkg(p)
    info["run_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return info
