"""M3: run the LLM audit agent (Groq) on every dataset contract.

Writes:
  results/llm/<run>/contracts/cNN.json   validated findings, rejected outputs, tokens, time
  results/llm/<run>/summary.json         machine, model, settings, totals, contract-level counts
  results/llm/<run>/SUMMARY.md           the same as tables

Usage:
  python scripts/run_llm.py --dry-run           # cost/time preview, no API key needed, no calls
  python scripts/run_llm.py --only c01          # one contract (live check)
  python scripts/run_llm.py                     # all contracts (stops safely at the caps)

Hard caps come from .env (see .env.example). If a cap is reached the run stops,
writes what it has, and exits with code 2; rerunning later skips finished contracts
because every response is cached in .cache/llm/.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from auditor.agent import PROMPT_VERSION, audit, make_slices, system_prompt, user_prompt
from auditor.dataset import DATASET_DIR, REPO_ROOT, load_labels
from auditor.llm import (
    DEFAULT_MODEL,
    BudgetExceeded,
    GroqClient,
    Ledger,
    LLMError,
    Limits,
    cost_usd,
    estimate_tokens,
)
from auditor.machine import machine_info
from auditor.report import contract_level, per_class_table
from auditor.solidity import function_spans


def prompts_for(src: str, threshold: int) -> list[str]:
    n = src.rstrip("\n").count("\n") + 1
    if n <= threshold or not function_spans(src):
        return [user_prompt(src)]
    return [user_prompt(src, keep, name) for name, keep in make_slices(src)]


def dry_run(entries: list[dict], model: str, threshold: int, limits: Limits) -> None:
    sys_tokens = estimate_tokens(system_prompt())
    calls = prompt_tokens = 0
    sliced = 0
    for e in entries:
        ps = prompts_for((DATASET_DIR / e["file"]).read_text(), threshold)
        sliced += len(ps) > 1
        calls += len(ps)
        prompt_tokens += sum(sys_tokens + estimate_tokens(p) for p in ps)
    worst_completion = calls * limits.max_completion_tokens
    worst_total = prompt_tokens + worst_completion
    ledger = Ledger()
    print(f"model: {model}")
    print(f"contracts: {len(entries)}, sliced: {sliced}, API calls: {calls}")
    print(f"estimated prompt tokens: {prompt_tokens}")
    print(f"worst-case completion tokens (calls x {limits.max_completion_tokens}): {worst_completion}")
    print(f"worst-case total tokens: {worst_total}")
    print(f"worst-case cost at paid-tier prices: ${cost_usd(model, prompt_tokens, worst_completion):.4f} "
          f"(Free plan: $0, requests over the limit are refused, not billed)")
    print(f"caps: {limits.daily_tokens} tokens/day, ${limits.total_usd:.2f} total, "
          f"{limits.tokens_per_minute} tokens/min, {limits.requests_per_minute} requests/min")
    print(f"already used today (UTC): {ledger.tokens_today()} tokens; "
          f"total so far: {ledger.data['total_tokens']} tokens, ${ledger.data['total_usd']:.4f}")
    print("cached responses are reused at no cost; the daily cap check uses the worst case per call")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--run", default="llm_only", help="results/llm/<run>/")
    ap.add_argument("--slice-threshold", type=int, default=150,
                    help="contracts longer than this many lines are audited per function")
    ap.add_argument("--reasoning-effort", default="low", choices=["low", "medium", "high"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    entries = load_labels()
    if args.only:
        entries = [e for e in entries if e["id"] in set(args.only)]
        if not entries:
            sys.exit("no matching contract ids")
    limits = Limits.from_settings()
    if args.dry_run:
        dry_run(entries, args.model, args.slice_threshold, limits)
        return

    client = GroqClient(model=args.model, limits=limits)
    out = REPO_ROOT / "results" / "llm" / args.run
    (out / "contracts").mkdir(parents=True, exist_ok=True)

    results: dict[str, dict] = {}
    stopped = None
    for i, e in enumerate(entries, start=1):
        src = (DATASET_DIR / e["file"]).read_text()
        try:
            r = audit(src, client, args.slice_threshold, args.reasoning_effort)
        except BudgetExceeded as exc:
            stopped = f"budget cap reached before {e['id']}: {exc}"
            print(f"\nSTOPPED: {stopped}", flush=True)
            break
        except LLMError as exc:
            stopped = f"API error on {e['id']}: {exc}"
            print(f"\nSTOPPED: {stopped}", flush=True)
            break
        rec = {"id": e["id"], "model": args.model, "prompt_version": PROMPT_VERSION,
               **{k: getattr(r, k) for k in r.__dataclass_fields__}}
        results[e["id"]] = rec
        (out / "contracts" / f"{e['id']}.json").write_text(json.dumps(rec, indent=2) + "\n")
        src_note = "cached" if r.cached_calls == r.calls else f"{r.api_seconds:.1f}s API"
        print(f"[{i:2d}/{len(entries)}] {e['id']} {r.mode} findings={len(r.findings)} "
              f"rejected={len(r.rejected)} tokens={r.prompt_tokens + r.completion_tokens} ({src_note})",
              flush=True)

    done = [e for e in entries if e["id"] in results]
    recs = [results[e["id"]] for e in done]
    pt = sum(r["prompt_tokens"] for r in recs)
    ct = sum(r["completion_tokens"] for r in recs)
    api_times = [r["api_seconds"] for r in recs]
    summary = {
        "machine": machine_info(),
        "model": args.model,
        "prompt_version": PROMPT_VERSION,
        "settings": {"reasoning_effort": args.reasoning_effort, "temperature": 0,
                     "slice_threshold": args.slice_threshold,
                     "max_completion_tokens": limits.max_completion_tokens},
        "contracts_requested": len(entries),
        "contracts_done": len(done),
        "stopped": stopped,
        "api_calls": sum(r["calls"] for r in recs),
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "tokens_per_contract_mean": round((pt + ct) / len(recs), 1) if recs else None,
        "cost_usd_at_paid_prices": round(cost_usd(args.model, pt, ct), 6),
        "api_seconds_total": round(sum(api_times), 1),
        "api_seconds_median": round(statistics.median(api_times), 2) if api_times else None,
        "rejected_findings": sum(len(r["rejected"]) for r in recs),
    }
    if done:
        summary.update(contract_level(done, results))
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    L = [f"# LLM agent run `{args.run}` (M3)", "",
         "Generated by `scripts/run_llm.py`. Numbers are from the machine below; API time is "
         "Groq's server round-trip, not local compute.", "", "| setting | value |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in summary["machine"].items()]
    L += [f"| model | {args.model} |", f"| prompt version | {PROMPT_VERSION} |"]
    L += [f"| {k} | {v} |" for k, v in summary["settings"].items()]
    L += ["", "## Totals", "", "| metric | value |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in summary.items() if not isinstance(v, (dict, list))]
    if done:
        L += ["", "## Per class (contract level)", ""] + per_class_table(summary["per_class"])
        L += ["", "## Per contract", "",
              "| id | label | true classes | LLM classes (function, confidence) | rejected | tokens |",
              "|---|---|---|---|---|---|"]
        for e in done:
            r = results[e["id"]]
            pred = "; ".join(f"{f['class']} ({f['function_from_line']}, {f['confidence']:.2f})"
                             for f in r["findings"]) or "-"
            L.append(f"| {e['id']} | {e['label']} | {', '.join(e['classes']) or '-'} | {pred} | "
                     f"{len(r['rejected'])} | {r['prompt_tokens'] + r['completion_tokens']} |")
    (out / "SUMMARY.md").write_text("\n".join(L) + "\n")

    print(f"\ndone: {len(done)}/{len(entries)} contracts, {summary['api_calls']} API calls")
    print(f"tokens: {pt} prompt + {ct} completion = {pt + ct} "
          f"(cost at paid-tier prices ${summary['cost_usd_at_paid_prices']:.4f}; Free plan $0)")
    if done:
        print(f"vulnerable flagged (any class): {summary['vulnerable_flagged_any_class']}/"
              f"{summary['vulnerable_contracts']}")
        print(f"clean flagged (any class): {summary['clean_flagged_any_class']}/{summary['clean_contracts']}")
        print(f"rejected (malformed) findings: {summary['rejected_findings']}")
    print(f"wrote {out}")
    if stopped:
        sys.exit(2)


if __name__ == "__main__":
    main()
