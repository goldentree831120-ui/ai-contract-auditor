"""Evaluate the SWC retriever on its own (no API calls, deterministic).

For each vulnerable contract: is a labeled SWC ID among the top-k retrieved entries
(exact), and is any retrieved entry in one of its labeled classes (class level)?
Reports both knowledge-base variants so the M4 design change is reproducible.

Writes results/retrieval/summary.json and results/retrieval/SUMMARY.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from auditor.dataset import DATASET_DIR, REPO_ROOT, load_labels, load_taxonomy
from auditor.kb import BM25, load_kb, taxonomy_entries


def evaluate(entries: list[dict], k: int) -> dict:
    swc2cls = {s: c for c, v in load_taxonomy()["classes"].items() for s in v["swc"]}
    bm = BM25(entries)
    rows, exact, cls = [], 0, 0
    vuln = [e for e in load_labels() if e["label"] == "vulnerable"]
    for e in vuln:
        top = [x["id"] for x, _ in bm.top((DATASET_DIR / e["file"]).read_text(), k)]
        gold = sorted({f["swc"] for f in e["findings"]})
        hit = bool(set(gold) & set(top))
        chit = bool(set(e["classes"]) & {swc2cls.get(t) for t in top})
        exact += hit
        cls += chit
        rows.append({"id": e["id"], "gold_swc": gold, "retrieved": top, "exact": hit, "class_level": chit})
    return {"kb_entries": len(entries), "k": k, "contracts": len(vuln),
            "recall_exact_swc": exact, "recall_class_level": cls, "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--out", default=str(REPO_ROOT / "results" / "retrieval"))
    args = ap.parse_args()
    full = evaluate(load_kb(), args.k)
    used = evaluate(taxonomy_entries(), args.k)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps({"all_swc_entries": full, "taxonomy_entries_used": used},
                                                 indent=2) + "\n")
    L = ["# Retrieval evaluation (M4)", "",
         "BM25 over SWC Title/Description/Remediation text; query = the contract's code. "
         f"Top-{args.k} entries, {used['contracts']} vulnerable contracts. No API calls.", "",
         "| knowledge base | entries | labeled SWC in top-k | labeled class in top-k |", "|---|---|---|---|",
         f"| all SWC entries (first design) | {full['kb_entries']} | {full['recall_exact_swc']}/{full['contracts']} "
         f"| {full['recall_class_level']}/{full['contracts']} |",
         f"| taxonomy entries only (used) | {used['kb_entries']} | {used['recall_exact_swc']}/{used['contracts']} "
         f"| {used['recall_class_level']}/{used['contracts']} |", "",
         "The restriction to taxonomy entries was decided after measuring the first design once, "
         "and not tuned further. Both rows use the same 31 contracts, so the second number is "
         "optimistic.", "", "## Per contract (knowledge base used)", "",
         "| id | labeled SWC | retrieved | exact | class |", "|---|---|---|---|---|"]
    for r in used["rows"]:
        L.append(f"| {r['id']} | {', '.join(r['gold_swc'])} | {', '.join(r['retrieved'])} | "
                 f"{'yes' if r['exact'] else '-'} | {'yes' if r['class_level'] else '-'} |")
    (out / "SUMMARY.md").write_text("\n".join(L) + "\n")
    print(f"all SWC entries ({full['kb_entries']}): labeled SWC in top-{args.k} "
          f"{full['recall_exact_swc']}/{full['contracts']}, class {full['recall_class_level']}/{full['contracts']}")
    print(f"taxonomy entries ({used['kb_entries']}, used): labeled SWC in top-{args.k} "
          f"{used['recall_exact_swc']}/{used['contracts']}, class {used['recall_class_level']}/{used['contracts']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
