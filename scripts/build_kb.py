"""Build knowledge/swc_kb.json from the SWC registry (pinned commit), text only.

Usage:
  python scripts/build_kb.py           # write knowledge/swc_kb.json
  python scripts/build_kb.py --check   # fail if the committed file differs from a fresh build
"""

from __future__ import annotations

import argparse
import json
import sys

from auditor.kb import KB_FILE, SWC, build_entries
from auditor.sources import fetch


def render() -> str:
    entries = build_entries(fetch(SWC["repo"], SWC["commit"]))
    data = {
        "source": f"https://github.com/{SWC['repo']}/tree/{SWC['commit']}/entries/docs",
        "license": "MIT (SWC-registry); see dataset/licenses/swc-MIT.txt",
        "kept_sections": ["Title", "Description", "Remediation"],
        "dropped": ["Samples (all code)", "References", "Relationships", "fenced code anywhere"],
        "entries": entries,
    }
    return json.dumps(data, indent=2) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = render()
    if args.check:
        if not KB_FILE.exists() or KB_FILE.read_text() != text:
            print("knowledge/swc_kb.json is out of date; run scripts/build_kb.py")
            sys.exit(1)
        print("check passed: knowledge base matches a fresh build from the pinned SWC commit")
        return
    KB_FILE.parent.mkdir(parents=True, exist_ok=True)
    KB_FILE.write_text(text)
    n = len(json.loads(text)["entries"])
    words = sum(len((e["description"] + " " + e["remediation"]).split()) for e in json.loads(text)["entries"])
    print(f"wrote {KB_FILE} ({n} entries, {words} words)")


if __name__ == "__main__":
    main()
