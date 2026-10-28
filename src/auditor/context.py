"""Extra prompt context for the M4 ablation: Slither output and retrieved SWC text."""

from __future__ import annotations

import json
import re

from auditor.dataset import REPO_ROOT
from auditor.kb import passage, retrieve

SLITHER_DIR = REPO_ROOT / "results" / "slither" / "contracts"
# Fixed before any M4 run: Informational and Optimization results are style/gas notes.
SLITHER_IMPACTS = ("High", "Medium", "Low")
_FILE = re.compile(r"[\w./-]*c\d{2}\.sol")


def slither_context(contract_id: str) -> str:
    path = SLITHER_DIR / f"{contract_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run scripts/run_slither.py first")
    return slither_context_from_findings(json.loads(path.read_text()).get("findings", []))


def slither_context_from_findings(findings: list[dict], file_name: str | None = None) -> str:
    """Prompt text from parsed Slither findings; file names are replaced by contract.sol."""
    rows = []
    for f in findings:
        if f["impact"] not in SLITHER_IMPACTS:
            continue
        desc = _FILE.sub("contract.sol", f["description"])
        if file_name:
            desc = re.sub(r"[\w./-]*" + re.escape(file_name), "contract.sol", desc)
        lines = f"lines {f['lines'][0]}-{f['lines'][-1]}" if f["lines"] else "no line"
        rows.append(f"- [{f['impact']} impact, {f['confidence']} confidence] {f['check']}: {desc} ({lines})")
    body = "\n".join(rows) if rows else "- (no findings of Low impact or above)"
    return ("Static analyzer output (Slither). It can contain false positives and misses; "
            "use it as a hint, not as ground truth:\n" + body)


def rag_context(code: str, k: int = 3) -> str:
    hits = retrieve(code, k)
    body = "\n\n".join(passage(e) for e, _ in hits) if hits else "(nothing retrieved)"
    return ("Reference notes on known weakness types, retrieved automatically by keyword match. "
            "They may not apply to this contract:\n" + body)


def build_context(kind: str, contract_id: str, code: str) -> str | None:
    parts = []
    if kind in ("rag", "both"):
        parts.append(rag_context(code))
    if kind in ("slither", "both"):
        parts.append(slither_context(contract_id))
    if kind not in ("none", "rag", "slither", "both"):
        raise ValueError(f"unknown context kind {kind!r}")
    return "\n\n".join(parts) or None
