"""Evaluation metrics (M5): per-class precision/recall/F1 at two granularities.

Units of comparison
- contract level: (contract, class). Predicted if the tool reports that class
  anywhere in the contract; true if the contract is labeled with that class.
- function level: (contract, class, function). The LLM's function is
  `function_from_line` (derived from its line number, not its own label); a Slither
  finding predicts every function it names, or "<contract-level>" if it names none.

Precision is undefined (None) when a tool makes no prediction for a class; recall
and F1 are then 0, so a class a tool cannot detect counts against it. Micro averages
pool all units; macro averages per class (undefined precision counts as 0 there).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from auditor.dataset import REPO_ROOT, load_labels, load_taxonomy

RESULTS = REPO_ROOT / "results"


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None  # 0 when nothing is found
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": None if p is None else round(p, 3),
            "recall": None if r is None else round(r, 3),
            "f1": None if f is None else round(f, 3)}


def load_tool(name: str) -> dict[str, list[dict]] | None:
    """{contract id: [findings with class, functions]} for 'slither' or an LLM run dir."""
    d = RESULTS / "slither" / "contracts" if name == "slither" else RESULTS / "llm" / name / "contracts"
    ids = [e["id"] for e in load_labels()]
    if not all((d / f"{i}.json").exists() for i in ids):
        return None  # missing or partial run: not comparable
    out = {}
    for i in ids:
        rec = json.loads((d / f"{i}.json").read_text())
        rows = []
        for f in rec.get("findings", []):
            if not f.get("class"):
                continue  # unmapped Slither detector
            fns = f["functions"] if "functions" in f else [f["function_from_line"]]
            rows.append({**f, "fns": fns or ["<contract-level>"]})
        out[i] = rows
    return out


def units(preds: dict[str, list[dict]]) -> tuple[set, set]:
    contract = {(cid, f["class"]) for cid, fs in preds.items() for f in fs}
    function = {(cid, f["class"], fn) for cid, fs in preds.items() for f in fs for fn in f["fns"]}
    return contract, function


def gold_units(entries: list[dict] | None = None) -> tuple[set, set]:
    entries = entries or load_labels()
    contract = {(e["id"], f["class"]) for e in entries for f in e["findings"]}
    function = {(e["id"], f["class"], f["function"]) for e in entries for f in e["findings"]}
    return contract, function


def scores(pred: set, gold: set, classes: list[str]) -> dict:
    per = {}
    for c in classes:
        p = {u for u in pred if u[1] == c}
        g = {u for u in gold if u[1] == c}
        per[c] = _prf(len(p & g), len(p - g), len(g - p))
    micro = _prf(len(pred & gold), len(pred - gold), len(gold - pred))
    macro = {k: round(sum(v[k] or 0.0 for v in per.values()) / len(per), 3)
             for k in ("precision", "recall", "f1")}
    return {"per_class": per, "micro": micro, "macro": macro}


def detection(preds: dict[str, list[dict]], entries: list[dict]) -> dict:
    """Binary task: is the contract vulnerable (any mapped finding = yes)?"""
    tp = sum(bool(preds[e["id"]]) and e["label"] == "vulnerable" for e in entries)
    fp = sum(bool(preds[e["id"]]) and e["label"] == "clean" for e in entries)
    fn = sum(not preds[e["id"]] and e["label"] == "vulnerable" for e in entries)
    return _prf(tp, fp, fn)


def bootstrap_micro_f1(preds: dict[str, list[dict]], entries: list[dict], n: int = 1000,
                       seed: int = 0) -> tuple[float, float]:
    """95% percentile interval for contract-level micro-F1, resampling contracts."""
    rng = random.Random(seed)
    gold = {e["id"]: {f["class"] for f in e["findings"]} for e in entries}
    pred = {cid: {f["class"] for f in fs} for cid, fs in preds.items()}
    ids = [e["id"] for e in entries]
    vals = []
    for _ in range(n):
        tp = fp = fn = 0
        for cid in (rng.choice(ids) for _ in ids):
            tp += len(pred[cid] & gold[cid])
            fp += len(pred[cid] - gold[cid])
            fn += len(gold[cid] - pred[cid])
        vals.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    vals.sort()
    return round(vals[int(0.025 * n)], 3), round(vals[int(0.975 * n) - 1], 3)


def classes() -> list[str]:
    return list(load_taxonomy()["classes"])


def evaluate_tool(name: str) -> dict | None:
    preds = load_tool(name)
    if preds is None:
        return None
    entries = load_labels()
    gc, gf = gold_units(entries)
    pc, pf = units(preds)
    lo, hi = bootstrap_micro_f1(preds, entries)
    return {
        "contract_level": scores(pc, gc, classes()),
        "function_level": scores(pf, gf, classes()),
        "detection": detection(preds, entries),
        "contract_micro_f1_95ci": [lo, hi],
        "predictions": preds,
    }


def run_dirs() -> list[str]:
    d = RESULTS / "llm"
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


def summary_of(name: str) -> dict:
    p = (RESULTS / "slither" / "summary.json") if name == "slither" else (RESULTS / "llm" / name / "summary.json")
    return json.loads(Path(p).read_text()) if Path(p).exists() else {}
