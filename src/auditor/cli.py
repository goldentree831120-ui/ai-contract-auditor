"""Command-line auditor (M6).

  auditor audit Contract.sol                  LLM audit, Markdown report
  auditor audit Contract.sol --slither --rag  add Slither output and retrieved SWC notes
  auditor audit Contract.sol --format json    machine-readable output
  auditor audit Contract.sol --dry-run        show the token/cost estimate, send nothing

The same caps, cache and validation as the benchmark apply (see .env.example).
Local analysis only: the file is read from disk, nothing is deployed or sent on-chain.

Exit codes: 0 = audited (findings or not), 2 = stopped by a cap or an API/network
error, 3 = bad input (missing file, unsupported compiler, ...).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from auditor.agent import PROMPT_VERSION, audit, system_prompt, user_prompt
from auditor.context import rag_context, slither_context_from_findings
from auditor.llm import DEFAULT_MODEL, BudgetExceeded, GroqClient, Limits, LLMError, cost_usd, estimate_tokens
from auditor.solc import PINNED_SHA256

MAX_BYTES = 200_000


class InputError(Exception):
    pass


def _ver(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def pick_solc(src: str, forced: str | None = None) -> str:
    """Choose a pinned solc version that satisfies the file's pragma.

    Supports the common forms: exact `0.4.24`, caret `^0.4.19`, and `>=a <b` ranges.
    Picks the highest pinned version that satisfies it.
    """
    pinned = sorted(PINNED_SHA256, key=_ver)
    if forced:
        if forced not in PINNED_SHA256:
            raise InputError(f"solc {forced} is not pinned; pinned versions: {', '.join(pinned)}")
        return forced
    m = re.search(r"pragma\s+solidity\s+([^;]+);", src)
    if not m:
        raise InputError("no `pragma solidity` line; pass --solc with one of: " + ", ".join(pinned))
    spec = m.group(1).strip()
    clauses = re.findall(r"(\^|>=|<=|>|<|=)?\s*(\d+\.\d+\.\d+)", spec)
    if not clauses:
        raise InputError(f"cannot read pragma {spec!r}; pass --solc")

    def ok(v: tuple[int, ...]) -> bool:
        for op, raw in clauses:
            t = _ver(raw)
            if op == "^" and not (v >= t and v[:2] == t[:2]):
                return False
            if op in ("", "=") and v != t:
                return False
            if op == ">=" and not v >= t:
                return False
            if op == ">" and not v > t:
                return False
            if op == "<=" and not v <= t:
                return False
            if op == "<" and not v < t:
                return False
        return True

    fits = [v for v in pinned if ok(_ver(v))]
    if not fits:
        raise InputError(f"pragma {spec!r} needs a solc version that is not pinned "
                         f"(pinned: {', '.join(pinned)}); Slither cannot run, use the audit without --slither")
    return fits[-1]


def build_context(src: str, path: Path, use_slither: bool, use_rag: bool, solc: str | None) -> tuple[str | None, dict]:
    parts, meta = [], {}
    if use_rag:
        parts.append(rag_context(src))
    if use_slither:
        from auditor.slither_runner import run_one

        version = pick_solc(src, solc)
        r = run_one(path, version)
        if not r["success"]:
            raise InputError(f"Slither failed with solc {version}: {str(r['error'])[:300]}")
        meta = {"solc": version, "slither_seconds": r["seconds"],
                "slither_findings": [f for f in r["findings"] if f["impact"] in ("High", "Medium", "Low")]}
        parts.append(slither_context_from_findings(r["findings"], path.name))
    return ("\n\n".join(parts) or None), meta


def to_markdown(path: Path, findings: list[dict], info: dict) -> str:
    L = [f"# Audit: {path.name}", "",
         f"Model `{info['model']}` (prompt {PROMPT_VERSION}), context: {info['context']}. "
         f"Tokens {info['tokens']}, API time {info['api_seconds']} s"
         + (", answered from cache" if info["cached"] else "") + ".", ""]
    if findings:
        L += ["| line | class | function | confidence | reasoning |", "|---|---|---|---|---|"]
        for f in findings:
            L.append(f"| {f['line']} | {f['class']} | {f['function_from_line']} | {f['confidence']:.2f} | "
                     f"{f['reasoning'].replace('|', '/')} |")
    else:
        L.append("No findings reported.")
    if info.get("slither_findings"):
        L += ["", f"Slither 0.11.6 (solc {info['solc']}) findings of Low impact or above, given to the model:", ""]
        L += [f"- {f['check']} ({f['impact']}): {f['description']}" for f in info["slither_findings"]]
    L += ["", "_Findings are model output, not verified vulnerabilities. On the project's 49-contract "
          "benchmark this model had contract-level F1 of about 0.6 and reported issues on 4 to 9 of 18 "
          "clean contracts per run; review every finding by hand._"]
    return "\n".join(L) + "\n"


def cmd_audit(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        raise InputError(f"file not found: {path}")
    if path.stat().st_size > MAX_BYTES:
        raise InputError(f"file is larger than {MAX_BYTES} bytes; audit a smaller file")
    src = path.read_text(errors="replace")
    if "contract" not in src and "library" not in src and "interface" not in src:
        raise InputError("this does not look like Solidity source")
    kind = "+".join(k for k, on in (("slither", args.slither), ("rag", args.rag)) if on) or "none"
    limits = Limits.from_settings()

    if args.dry_run:
        prompt = estimate_tokens(system_prompt() + user_prompt(src, context="x" * (1500 if args.rag else 0)))
        worst = prompt + limits.max_completion_tokens
        print(f"file: {path} ({src.count(chr(10)) + 1} lines), context: {kind}")
        print(f"estimated prompt tokens: {prompt}; worst case per call: {worst} "
              f"(${cost_usd(args.model, prompt, limits.max_completion_tokens):.4f} at paid-tier prices; "
              f"Free plan $0)")
        print(f"files over {args.slice_threshold} lines are audited per function (one call each)")
        return 0

    context, meta = build_context(src, path, args.slither, args.rag, args.solc)
    client = GroqClient(model=args.model, limits=limits)
    r = audit(src, client, args.slice_threshold, args.reasoning_effort, context)
    info = {"file": str(path), "model": args.model, "prompt_version": PROMPT_VERSION, "context": kind,
            "mode": r.mode, "calls": r.calls, "cached": r.cached_calls == r.calls,
            "tokens": r.prompt_tokens + r.completion_tokens, "api_seconds": r.api_seconds, **meta}
    if args.format == "json":
        print(json.dumps({**info, "findings": r.findings, "rejected": r.rejected}, indent=2))
    else:
        print(to_markdown(path, r.findings, info), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="auditor", description="LLM smart-contract auditor (local files only)")
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser("audit", help="audit one Solidity file")
    a.add_argument("file")
    a.add_argument("--slither", action="store_true", help="run Slither first and give its output to the model")
    a.add_argument("--rag", action="store_true", help="add retrieved SWC weakness descriptions")
    a.add_argument("--solc", help="compiler version for --slither (default: chosen from the pragma)")
    a.add_argument("--format", choices=["md", "json"], default="md")
    a.add_argument("--model", default=DEFAULT_MODEL)
    a.add_argument("--reasoning-effort", default="low", choices=["low", "medium", "high"])
    a.add_argument("--slice-threshold", type=int, default=150)
    a.add_argument("--dry-run", action="store_true", help="estimate tokens and cost, send nothing")
    args = ap.parse_args(argv)
    try:
        return cmd_audit(args)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    except (BudgetExceeded, LLMError) as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
