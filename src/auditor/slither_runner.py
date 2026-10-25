"""Run Slither on one contract and normalize its JSON output."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from auditor.slither_map import map_detector
from auditor.solc import solc_path


def parse_results(data: dict) -> list[dict]:
    """Turn Slither's --json output into a flat list of findings.

    Each finding keeps Slither's own detector name, impact and confidence, the
    class it maps to (or None), the source lines it points at, and the functions
    those lines belong to.
    """
    findings = []
    for r in (data.get("results") or {}).get("detectors", []):
        elements = r.get("elements", [])
        nodes = [e for e in elements if e.get("type") == "node"]
        pointed = nodes or elements
        lines = sorted({ln for e in pointed for ln in e.get("source_mapping", {}).get("lines", [])})
        functions = {e["name"] for e in elements if e.get("type") == "function"}
        for e in nodes:
            parent = (e.get("type_specific_fields") or {}).get("parent") or {}
            if parent.get("type") == "function":
                functions.add(parent.get("name"))
        findings.append({
            "check": r.get("check"),
            "impact": r.get("impact"),
            "confidence": r.get("confidence"),
            "class": map_detector(r.get("check", "")),
            "lines": lines,
            "functions": sorted(f for f in functions if f),
            "description": (r.get("description") or "").strip().split("\n")[0][:300],
        })
    return findings


def slither_bin() -> str:
    """The slither executable from the same environment as this Python, else PATH."""
    local = Path(sys.executable).parent / "slither"
    found = str(local) if local.exists() else shutil.which("slither")
    if not found:
        raise RuntimeError("slither not found; install with: pip install -e '.[slither]'")
    return found


def run_one(contract: Path, solc_version: str, raw_out: Path | None = None) -> dict:
    """Run Slither on one file. Returns timing, status and parsed findings."""
    solc = solc_path(solc_version)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "slither.json"
        start = time.perf_counter()
        proc = subprocess.run(
            [slither_bin(), str(contract), "--solc", str(solc), "--json", str(out), "--disable-color"],
            capture_output=True, text=True,
        )
        seconds = time.perf_counter() - start
        data = json.loads(out.read_text()) if out.exists() else {}
    if raw_out is not None:
        raw_out.parent.mkdir(parents=True, exist_ok=True)
        raw_out.write_text(json.dumps(data, indent=1))
    success = bool(data.get("success"))
    return {
        "seconds": round(seconds, 3),
        "success": success,
        "error": None if success else (data.get("error") or proc.stderr.strip()[-500:] or "no output"),
        "findings": parse_results(data) if success else [],
    }
