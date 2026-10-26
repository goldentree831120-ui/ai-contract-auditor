"""Combine Slither and the four LLM runs into one ablation table (no API calls).

Reads results/slither/summary.json and results/llm/<run>/summary.json, writes
results/ablation/ABLATION.md and results/ablation/summary.json. Runs that do not exist
yet are listed as "not run". Precision/recall/F1 per class are added in M5.
"""

from __future__ import annotations

import json

from auditor.dataset import REPO_ROOT, load_taxonomy

RUNS = [
    ("Slither 0.11.6 (M2)", REPO_ROOT / "results" / "slither" / "summary.json"),
    ("LLM only", REPO_ROOT / "results" / "llm" / "llm_only" / "summary.json"),
    ("LLM + Slither", REPO_ROOT / "results" / "llm" / "llm_slither" / "summary.json"),
    ("LLM + RAG", REPO_ROOT / "results" / "llm" / "llm_rag" / "summary.json"),
    ("LLM + RAG + Slither", REPO_ROOT / "results" / "llm" / "llm_both" / "summary.json"),
]


def load(path):
    if not path.exists():
        return None
    s = json.loads(path.read_text())
    if s.get("contracts_done", s.get("contracts_analyzed_ok")) != s.get("contracts_requested",
                                                                         s.get("contracts_total")):
        return None  # partial run: not comparable
    return s


def flagged(s, label):
    key = f"{label}_flagged_any_class" if f"{label}_flagged_any_class" in s else f"{label}_flagged_any_mapped_class"
    return f"{s[key]}/{s[f'{label}_contracts']}"


def main() -> None:
    rows = [(name, load(p)) for name, p in RUNS]
    classes = list(load_taxonomy()["classes"])
    L = ["# Ablation (M4)", "",
         "Contract level: a contract counts as flagged for a class if the tool reports that class "
         "anywhere in it. Hit = flagged on a contract that has the class; false alarm = flagged on "
         "one that does not. Same 49 contracts, model, prompt and settings in every LLM row; only the "
         "added context differs.", "",
         "| condition | vulnerable flagged | clean flagged | tokens (prompt + completion) | tokens per contract |",
         "|---|---|---|---|---|"]
    for name, s in rows:
        if s is None:
            L.append(f"| {name} | not run | | | |")
            continue
        if "prompt_tokens" in s:
            tok = f"{s['prompt_tokens']} + {s['completion_tokens']}"
            per = s["tokens_per_contract_mean"]
        else:
            tok, per = "n/a (local tool)", "n/a"
        L.append(f"| {name} | {flagged(s, 'vulnerable')} | {flagged(s, 'clean')} | {tok} | {per} |")
    L += ["", "## Per class: hits / false alarms", "",
          "| class | n | " + " | ".join(name for name, _ in rows) + " |",
          "|---|---|" + "---|" * len(rows)]
    for c in classes:
        n = next((s["per_class"][c]["contracts_with_class"] for _, s in rows if s), "?")
        cells = []
        for _, s in rows:
            if s is None:
                cells.append("-")
            else:
                v = s["per_class"][c]
                cells.append(f"{v['flagged_with_this_class']} / {v['flagged_without_having_it']}")
        L.append(f"| {c} | {n} | " + " | ".join(cells) + " |")
    out = REPO_ROOT / "results" / "ablation"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ABLATION.md").write_text("\n".join(L) + "\n")
    (out / "summary.json").write_text(json.dumps(
        {name: (None if s is None else {k: s[k] for k in s if k not in ("machine",)}) for name, s in rows},
        indent=2) + "\n")
    print("\n".join(L[5:5 + len(rows) + 1]))
    print(f"wrote {out / 'ABLATION.md'}")


if __name__ == "__main__":
    main()
