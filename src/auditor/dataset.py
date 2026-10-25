"""Load and validate the labeled evaluation dataset (dataset/labels.json)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from auditor.solidity import find_anchor, has_comments, identifiers, squash

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"

LABELS = {"vulnerable", "clean"}
ROLES = {"vulnerable_sample", "fixed_sample", "negative_sample", "fixed_sample_residual"}
MIN_CONTRACTS, MAX_CONTRACTS = 30, 50

# Identifier fragments that would reveal the label or class to a model.
LEAK_RE = re.compile(
    r"fixed|safe|vuln|exploit|attack|overflow|underflow|reentr|entrancy|suicide|"
    r"malleab|checked|drain|anyone|dos|feasible|dependence|random|mutex|bug|insecure|hack",
    re.IGNORECASE,
)
# Language built-ins and library names that match LEAK_RE but carry no label signal
# (SafeMath appears in many clean AND vulnerable real contracts).
LEAK_ALLOW = {"suicide", "SafeMath"}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_taxonomy(root: Path = DATASET_DIR) -> dict:
    return json.loads((root / "taxonomy.json").read_text())


def load_labels(root: Path = DATASET_DIR) -> list[dict]:
    return json.loads((root / "labels.json").read_text())["contracts"]


def leaked_identifiers(src: str) -> list[str]:
    return sorted(i for i in identifiers(src) if i not in LEAK_ALLOW and LEAK_RE.search(i))


def validate(root: Path = DATASET_DIR) -> list[str]:
    """Return a list of problems; an empty list means the dataset is valid."""
    errors: list[str] = []
    classes = set(load_taxonomy(root)["classes"])
    entries = load_labels(root)

    if not MIN_CONTRACTS <= len(entries) <= MAX_CONTRACTS:
        errors.append(f"dataset has {len(entries)} contracts, expected {MIN_CONTRACTS}-{MAX_CONTRACTS}")

    seen_ids: set[str] = set()
    seen_hashes: dict[str, str] = {}
    seen_loose: dict[str, str] = {}
    for e in entries:
        cid = e.get("id", "?")
        for field in ("id", "file", "label", "role", "classes", "findings", "solc_version", "sha256", "source"):
            if field not in e:
                errors.append(f"{cid}: missing field {field}")
        if cid in seen_ids:
            errors.append(f"{cid}: duplicate id")
        seen_ids.add(cid)
        if e.get("label") not in LABELS:
            errors.append(f"{cid}: bad label {e.get('label')!r}")
        if e.get("role") not in ROLES:
            errors.append(f"{cid}: bad role {e.get('role')!r}")

        findings = e.get("findings", [])
        if e.get("label") == "vulnerable" and not findings:
            errors.append(f"{cid}: vulnerable but has no findings")
        if e.get("label") == "clean" and findings:
            errors.append(f"{cid}: clean but has findings")
        if sorted({f["class"] for f in findings}) != sorted(e.get("classes", [])):
            errors.append(f"{cid}: classes do not match findings")
        for c in e.get("classes", []):
            if c not in classes:
                errors.append(f"{cid}: unknown class {c!r}")

        src_info = e.get("source", {})
        lic = src_info.get("license_file_in_repo")
        if not lic or not (root / lic).exists():
            errors.append(f"{cid}: license file missing ({lic})")

        path = root / e.get("file", "")
        if not path.exists():
            errors.append(f"{cid}: file not found {path}")
            continue
        text = path.read_text()
        if sha256_text(text) != e.get("sha256"):
            errors.append(f"{cid}: sha256 mismatch")
        digest = sha256_text(text)
        if digest in seen_hashes:
            errors.append(f"{cid}: duplicate contract content (same as {seen_hashes[digest]})")
        seen_hashes[digest] = cid
        loose = squash(text)
        if loose in seen_loose:
            errors.append(f"{cid}: same code as {seen_loose[loose]} apart from whitespace")
        seen_loose[loose] = cid
        if has_comments(text):
            errors.append(f"{cid}: contains comments (label leak risk)")
        leaks = leaked_identifiers(text)
        if leaks:
            errors.append(f"{cid}: identifiers may leak the label: {leaks}")
        n_lines = text.count("\n")
        for f in findings:
            ln = f.get("line", 0)
            if not 1 <= ln <= n_lines:
                errors.append(f"{cid}: finding line {ln} out of range")
                continue
            if find_anchor(text, f["anchor"]) != [ln]:
                errors.append(f"{cid}: anchor does not uniquely match line {ln}")
    return errors


def summary(root: Path = DATASET_DIR) -> dict:
    entries = load_labels(root)
    per_class: dict[str, int] = {}
    for e in entries:
        for c in e["classes"]:
            per_class[c] = per_class.get(c, 0) + 1
    return {
        "contracts": len(entries),
        "vulnerable": sum(e["label"] == "vulnerable" for e in entries),
        "clean": sum(e["label"] == "clean" for e in entries),
        "findings": sum(len(e["findings"]) for e in entries),
        "per_class_contracts": dict(sorted(per_class.items())),
        "by_source": {
            s: sum(e["source"]["name"] == s for e in entries)
            for s in sorted({e["source"]["name"] for e in entries})
        },
    }
