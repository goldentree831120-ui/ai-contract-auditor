"""Build the labeled evaluation dataset from dataset/spec.toml.

Fetches every source repository at the pinned commit in the spec, extracts each
sample, sanitizes it (comments removed, label-revealing identifiers renamed),
locates each labeled finding by its anchor text, and writes:

  dataset/contracts/cNN.sol   sanitized contracts (the only files models see)
  dataset/raw/<key>.sol       verbatim original text, for provenance
  dataset/licenses/*.txt      license file of each source repo, verbatim
  dataset/labels.json         ground truth
  dataset/CONTRACTS.md        generated table of all contracts

Usage:
  python scripts/build_dataset.py            # build into dataset/
  python scripts/build_dataset.py --check    # rebuild in a temp dir, fail if dataset/ differs
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from auditor.solidity import (  # noqa: E402
    enclosing_function,
    find_anchor,
    pragma_version,
    sanitize,
    squash,
    strip_comments,
)

SPEC = REPO_ROOT / "dataset" / "spec.toml"
CACHE = REPO_ROOT / ".cache" / "sources"
GENERATED = ["contracts", "raw", "licenses", "labels.json", "CONTRACTS.md"]

# Used only to cross-check our line labels; no SmartBugs contracts are redistributed.
SMARTBUGS = {
    "repo": "smartbugs/smartbugs-curated",
    "commit": "230e649123477eff332742a59a1c7cc6dc286cab",
}
SMARTBUGS_NAMES = {  # our key -> SmartBugs file name, where names differ
    "swc118-incorrect_constructor_name1": "incorrect_constructor_name2.sol",
    "swc118-incorrect_constructor_name2": "incorrect_constructor_name3.sol",
    "tob-reentrancy": "reentrancy_simple.sol",
    "sigp-etherstore": "etherstore.sol",
    "sigp-timelock": "timelock.sol",
    "sigp-lotto": "lotto.sol",
    "sigp-roulette": "roulette.sol",
    "sigp-findthishash": "FindThisHash.sol",
}


def fetch(repo: str, commit: str) -> Path:
    """Shallow-fetch one commit of a GitHub repo into the cache (idempotent)."""
    dest = CACHE / repo.replace("/", "__")
    head = dest / ".git" / "HEAD"
    if dest.exists() and head.exists():
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


def swc_sample(root: Path, doc: str, sample: str) -> str:
    md = (root / "entries" / "docs" / f"{doc}.md").read_text()
    m = re.search(rf"^### {re.escape(sample)}\s*\n+```solidity\n(.*?)```", md, re.M | re.S)
    if not m:
        raise SystemExit(f"sample {sample} not found in {doc}")
    return m.group(1)


def sigp_block(root: Path, must_contain: list[str]) -> str:
    md = (root / "README.md").read_text()
    blocks = re.findall(r"```solidity\n(.*?)```", md, re.S)
    hits = [b for b in blocks if all(s in b for s in must_contain)]
    if len(hits) != 1:
        raise SystemExit(f"sigp block {must_contain} matched {len(hits)} blocks, need exactly 1")
    return hits[0]


def smartbugs_index(root: Path) -> dict[str, dict]:
    data = json.loads((root / "vulnerabilities.json").read_text())
    return {x["name"].lower(): x for x in data}


def crosscheck(entry: dict, text: str, renames: dict, sb_root: Path, sb_index: dict) -> dict | None:
    name = SMARTBUGS_NAMES.get(entry["key"], entry.get("sample", "")).lower()
    sb = sb_index.get(name)
    if not sb or entry["label"] != "vulnerable":
        return None
    # strip_comments keeps newlines, so SmartBugs line numbers stay valid.
    sb_text = strip_comments((sb_root / sb["path"]).read_text())
    for old in sorted(renames, key=len, reverse=True):  # same renames as our copy
        sb_text = re.sub(rf"\b{re.escape(old)}\b", renames[old], sb_text)
    sb_src = sb_text.split("\n")
    sb_marked = [ln for v in sb["vulnerabilities"] for ln in v["lines"] if 0 < ln <= len(sb_src)]
    sb_lines = {squash(sb_src[ln - 1]) for ln in sb_marked}
    sb_funcs = {enclosing_function(sb_text, ln) for ln in sb_marked}
    ours = text.split("\n")
    n = len(entry["findings"])
    on_line = sum(squash(ours[f["line"] - 1]) in sb_lines for f in entry["findings"])
    in_func = sum(f["function"] in sb_funcs for f in entry["findings"])
    return {
        "smartbugs_file": sb["path"],
        "smartbugs_classes": sorted({v["category"] for v in sb["vulnerabilities"]}),
        "our_findings_on_a_smartbugs_line": f"{on_line}/{n}",
        "our_findings_in_a_smartbugs_function": f"{in_func}/{n}",
    }


def build(out: Path) -> None:
    spec = tomllib.loads(SPEC.read_text())
    roots = {name: fetch(s["repo"], s["commit"]) for name, s in spec["sources"].items()}
    sb_root = fetch(SMARTBUGS["repo"], SMARTBUGS["commit"])
    sb_index = smartbugs_index(sb_root)

    for d in GENERATED:
        p = out / d
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    (out / "contracts").mkdir(parents=True)
    (out / "raw").mkdir()
    (out / "licenses").mkdir()

    for name, s in spec["sources"].items():
        shutil.copy(roots[name] / s["license_file"], out / "licenses" / f"{name}-{s['license']}.txt")

    built = []
    for c in spec["contract"]:
        src = spec["sources"][c["source"]]
        root = roots[c["source"]]
        if c["source"] == "swc":
            raw = swc_sample(root, c["doc"], c["sample"])
            origin_path = f"entries/docs/{c['doc']}.md#{c['sample']}"
        elif c["source"] == "tob":
            raw = (root / c["path"]).read_text()
            origin_path = c["path"]
        else:
            raw = sigp_block(root, c["block_match"])
            origin_path = "README.md (code block containing: " + " | ".join(c["block_match"]) + ")"
        text = sanitize(raw, c.get("renames"), c.get("prepend", ""))

        findings = []
        for f in c["findings"]:
            lines = find_anchor(text, f["anchor"])
            if len(lines) != 1:
                raise SystemExit(f"{c['key']}: anchor {f['anchor']!r} matched lines {lines}")
            findings.append({
                "class": f["class"], "swc": f["swc"], "line": lines[0],
                "function": enclosing_function(text, lines[0]), "anchor": f["anchor"],
            })

        credited = re.search(r"@source:\s*(\S+)", raw)
        author = re.search(r"@author:\s*(.+)", raw)
        mods = ["comments removed", "whitespace normalized"]
        if c.get("renames"):
            mods.append("identifiers renamed: " + ", ".join(f"{k}->{v}" for k, v in c["renames"].items()))
        if c.get("prepend"):
            mods.append(f"added '{c['prepend']}'")
        built.append({
            "key": c["key"], "text": text, "raw": raw, "label": c["label"], "role": c["role"],
            "pair": c.get("pair", ""), "classes": sorted({f["class"] for f in findings}),
            "findings": findings, "solc_version": c["solc"], "pragma": pragma_version(text),
            "sample": c.get("sample", ""), "renames": c.get("renames", {}),
            "source": {
                "name": c["source"], "repo": src["repo"], "commit": src["commit"],
                "path": origin_path, "license": src["license"],
                "license_file_in_repo": f"licenses/{c['source']}-{src['license']}.txt",
                "url": f"https://github.com/{src['repo']}/blob/{src['commit']}/"
                       + origin_path.split("#")[0].split(" (")[0],
                "credited_origin": credited.group(1) if credited else None,
                "credited_author": author.group(1).strip() if author else None,
            },
            "modifications": mods,
            "notes": c["notes"],
        })

    # Neutral IDs: ordered by content hash, so ID order carries no label information.
    built.sort(key=lambda b: hashlib.sha256(b["text"].encode()).hexdigest())
    labels = []
    for i, b in enumerate(built, start=1):
        cid = f"c{i:02d}"
        (out / "contracts" / f"{cid}.sol").write_text(b["text"])
        (out / "raw" / f"{b['key']}.sol").write_text(b["raw"])
        entry = {
            "id": cid, "file": f"contracts/{cid}.sol", "key": b["key"], "label": b["label"],
            "role": b["role"], "pair": b["pair"], "classes": b["classes"], "findings": b["findings"],
            "solc_version": b["solc_version"], "pragma": b["pragma"],
            "sha256": hashlib.sha256(b["text"].encode()).hexdigest(),
            "source": b["source"], "modifications": b["modifications"], "notes": b["notes"],
        }
        entry["smartbugs_crosscheck"] = crosscheck({**entry, "sample": b["sample"]}, b["text"], b["renames"], sb_root, sb_index)
        labels.append(entry)

    (out / "labels.json").write_text(json.dumps(
        {"version": 1, "generated_by": "scripts/build_dataset.py", "spec": "dataset/spec.toml",
         "contracts": labels}, indent=2) + "\n")
    write_table(out, labels)


def write_table(out: Path, labels: list[dict]) -> None:
    rows = ["# Contracts (generated by scripts/build_dataset.py, do not edit)", "",
            "| id | label | classes | role | function(s) | source | license | lines |",
            "|---|---|---|---|---|---|---|---|"]
    for e in labels:
        fns = ", ".join(sorted({f["function"] for f in e["findings"]})) or "-"
        rows.append(f"| {e['id']} | {e['label']} | {', '.join(e['classes']) or '-'} | {e['role']} | "
                    f"{fns} | [{e['key']}]({e['source']['url']}) | {e['source']['license']} | "
                    f"{(out / e['file']).read_text().count(chr(10))} |")
    (out / "CONTRACTS.md").write_text("\n".join(rows) + "\n")


def same_tree(a: Path, b: Path) -> list[str]:
    diffs = []
    for name in GENERATED:
        pa, pb = a / name, b / name
        if pa.is_dir() and pb.is_dir():
            cmp = filecmp.dircmp(pa, pb)
            stack = [cmp]
            while stack:
                d = stack.pop()
                diffs += [f"{name}: only in one side: {x}" for x in d.left_only + d.right_only]
                diffs += [f"{name}: differs: {x}" for x in d.diff_files]
                stack += d.subdirs.values()
        elif pa.is_file() and pb.is_file():
            if pa.read_bytes() != pb.read_bytes():
                diffs.append(f"{name}: differs")
        else:
            diffs.append(f"{name}: missing")
    return diffs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="rebuild in a temp dir and compare")
    args = ap.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            build(Path(tmp))
            diffs = same_tree(REPO_ROOT / "dataset", Path(tmp))
        if diffs:
            print("dataset/ is out of date with spec.toml:\n  " + "\n  ".join(diffs))
            sys.exit(1)
        print("check passed: committed dataset matches a fresh build from pinned sources")
    else:
        build(REPO_ROOT / "dataset")
        print("built dataset/ from spec.toml")


if __name__ == "__main__":
    main()
