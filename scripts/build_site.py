"""Build the static results explorer (M6): site/index.html, one self-contained file.

Reads only committed files (dataset, results/, results/eval/results.json); no API calls,
no server, no external scripts or fonts. Open site/index.html in a browser, or let CI
publish it to GitHub Pages.

Usage:
  python scripts/build_site.py              # write site/index.html
  python scripts/build_site.py --out DIR    # write somewhere else
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from auditor.dataset import DATASET_DIR, REPO_ROOT, load_labels, load_taxonomy
from auditor.metrics import evaluate_tool, run_dirs

TEMPLATE = REPO_ROOT / "scripts" / "site_template.html"
LABELS = {"slither": "Slither 0.11.6", "llm_only": "LLM only", "llm_slither": "LLM + Slither",
          "llm_rag": "LLM + RAG", "llm_both": "LLM + RAG + Slither"}


def label(run: str) -> str:
    base, _, rep = run.partition("_r")
    if run in LABELS:
        return LABELS[run]
    return f"{LABELS.get(base, base)} (repeat {rep})" if rep.isdigit() else run


def collect() -> dict:
    ev = json.loads((REPO_ROOT / "results" / "eval" / "results.json").read_text())
    runs = ["slither"] + run_dirs()
    preds = {}
    for r in runs:
        res = evaluate_tool(r)
        if res is None:
            continue
        preds[r] = {cid: [{"class": f["class"], "fns": f["fns"],
                           "lines": f.get("lines") or ([f["line"]] if "line" in f else []),
                           "confidence": f.get("confidence"),
                           "why": (f.get("reasoning") or f.get("description") or f.get("check") or "")[:400],
                           "check": f.get("check")}
                          for f in fs]
                    for cid, fs in res["predictions"].items()}
    contracts = []
    for e in load_labels():
        contracts.append({
            "id": e["id"], "label": e["label"], "role": e["role"], "classes": e["classes"],
            "findings": [{"class": f["class"], "swc": f["swc"], "line": f["line"], "function": f["function"]}
                         for f in e["findings"]],
            "notes": e["notes"], "source": e["source"]["url"], "license": e["source"]["license"],
            "code": (DATASET_DIR / e["file"]).read_text(),
        })
    metrics = {r: {k: ev[r][k] for k in ("contract_level", "function_level", "detection", "contract_micro_f1_95ci")}
               for r in runs if r in ev}
    return {
        "labels": {r: label(r) for r in preds},
        "base": [r for r in LABELS if r in preds],
        "classes": {c: v["summary"] for c, v in load_taxonomy()["classes"].items()},
        "metrics": metrics,
        "variance": ev.get("_variance", []),
        "fp": ev.get("_false_positives", {}),
        "missed": ev.get("_missed_by_all", []),
        "preds": preds,
        "contracts": contracts,
    }


def render(data: dict) -> str:
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text()
    assert html.count("__DATA__") == 1
    return html.replace("__DATA__", blob)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO_ROOT / "site"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    html = render(collect())
    (out / "index.html").write_text(html)
    print(f"wrote {out / 'index.html'} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
