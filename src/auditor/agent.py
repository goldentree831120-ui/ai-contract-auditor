"""LLM audit agent: one contract in, validated structured findings out.

The model sees only the sanitized contract text with line numbers. It never sees
the file name, the label, the SWC source or any hint about whether the contract is
vulnerable.

Contracts longer than `slice_threshold` lines are audited one function at a time:
each slice keeps every contract-level line (pragma, contract header, state
variables, events, closing braces) plus the signature line of every other function
and the full body of one function, with the original line numbers. Findings from
all slices are merged and de-duplicated by (class, function).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from auditor.dataset import load_taxonomy
from auditor.llm import GroqClient
from auditor.solidity import enclosing_function, function_spans

PROMPT_VERSION = "m3-v1"


def classes() -> dict[str, dict]:
    return load_taxonomy()["classes"]


def output_schema() -> dict:
    """JSON schema for strict structured output (all fields required, no extras)."""
    return {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "class": {"type": "string", "enum": sorted(classes())},
                        "function": {"type": "string"},
                        "line": {"type": "integer"},
                        "reasoning": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["class", "function", "line", "reasoning", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["findings"],
        "additionalProperties": False,
    }


def system_prompt() -> str:
    lines = [
        "You are a smart-contract security auditor reviewing Solidity code.",
        "Report only weaknesses that an attacker, miner or ordinary user could actually exploit "
        "in the code as written. Do not report style, gas, compiler-version or best-practice notes.",
        "If you find no exploitable weakness, return an empty findings list. Clean contracts are common.",
        "",
        "Use exactly one of these classes per finding:",
    ]
    for name, c in classes().items():
        lines.append(f"- {name}: {c['summary']}")
    lines += [
        "",
        "For each finding give:",
        "- class: one of the classes above",
        "- function: the name of the function, modifier or 'constructor'/'fallback' that contains the issue",
        "- line: the line number (as shown at the start of each line) of the most relevant statement",
        "- reasoning: one or two sentences on how it can be exploited",
        "- confidence: a number from 0 to 1",
        "Report each distinct issue once.",
    ]
    return "\n".join(lines)


def numbered(src: str, keep: set[int] | None = None) -> str:
    rows = src.rstrip("\n").split("\n")
    width = len(str(len(rows)))
    out = []
    for i, row in enumerate(rows, start=1):
        if keep is None or i in keep:
            out.append(f"{i:>{width}} | {row}")
    return "\n".join(out)


def make_slices(src: str) -> list[tuple[str, set[int]]]:
    """(function name, set of line numbers to show) for each function body."""
    spans = function_spans(src)
    n = src.rstrip("\n").count("\n") + 1
    inside = {ln for _, a, b in spans for ln in range(a, b + 1)}
    context = {ln for ln in range(1, n + 1) if ln not in inside}
    signatures = {a for _, a, _ in spans}
    return [(name, context | signatures | set(range(a, b + 1))) for name, a, b in spans]


def user_prompt(src: str, keep: set[int] | None = None, focus: str | None = None,
                context: str | None = None) -> str:
    head = "Audit this Solidity contract."
    if focus is not None:
        head = (f"Audit the function `{focus}` in this excerpt. Contract-level declarations and "
                "the signature lines of other functions are shown for context; their bodies are "
                "omitted. Report only issues inside the shown body of the function being audited.")
    # Without context the prompt is byte-identical to M3, so the llm_only run stays valid.
    extra = f"\n\n{context}" if context else ""
    return f"{head}{extra}\n\n```solidity\n{numbered(src, keep)}\n```"


@dataclass
class AuditResult:
    findings: list[dict]
    rejected: list[dict]
    mode: str
    calls: int
    cached_calls: int
    prompt_tokens: int
    completion_tokens: int
    seconds: float
    api_seconds: float


def validate_findings(raw: list, src: str, allowed_lines: set[int] | None = None) -> tuple[list, list]:
    """Keep well-formed findings; return (kept, rejected-with-reason)."""
    valid_classes = set(classes())
    n = src.rstrip("\n").count("\n") + 1
    kept, rejected = [], []
    for f in raw if isinstance(raw, list) else []:
        reason = None
        if not isinstance(f, dict):
            reason = "not an object"
        elif f.get("class") not in valid_classes:
            reason = f"unknown class {f.get('class')!r}"
        elif not isinstance(f.get("line"), int) or not 1 <= f["line"] <= n:
            reason = f"line {f.get('line')!r} outside 1..{n}"
        elif allowed_lines is not None and f["line"] not in allowed_lines:
            reason = f"line {f['line']} not shown in this slice"
        if reason:
            rejected.append({"finding": f, "reason": reason})
            continue
        conf = f.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) else 0.0
        kept.append({
            "class": f["class"],
            "function": str(f.get("function", "")),
            "line": f["line"],
            "function_from_line": enclosing_function(src, f["line"]),
            "reasoning": str(f.get("reasoning", ""))[:1000],
            "confidence": min(1.0, max(0.0, conf)),
        })
    return kept, rejected


def audit(src: str, client: GroqClient, slice_threshold: int = 150,
          reasoning_effort: str = "low", context: str | None = None,
          repeat: int = 0) -> AuditResult:
    n_lines = src.rstrip("\n").count("\n") + 1
    schema, system = output_schema(), system_prompt()
    if n_lines <= slice_threshold or not function_spans(src):
        jobs = [(None, None)]
        mode = "whole"
    else:
        jobs = [(name, keep) for name, keep in make_slices(src)]
        mode = "sliced"

    findings, rejected = [], []
    calls = cached = pt = ct = 0
    api_seconds = 0.0
    start = time.perf_counter()
    for focus, keep in jobs:
        resp = client.complete_json(system, user_prompt(src, keep, focus, context), schema,
                                    reasoning_effort=reasoning_effort, repeat=repeat)
        calls += 1
        cached += resp["cached"]
        pt += resp["usage"]["prompt_tokens"]
        ct += resp["usage"]["completion_tokens"]
        api_seconds += resp.get("seconds", 0.0)
        k, r = validate_findings(resp["content"].get("findings", []), src, keep)
        findings += k
        rejected += r

    merged: dict[tuple[str, str], dict] = {}
    for f in findings:
        key = (f["class"], f["function_from_line"])
        if key not in merged or f["confidence"] > merged[key]["confidence"]:
            merged[key] = f
    return AuditResult(
        findings=sorted(merged.values(), key=lambda f: (f["line"], f["class"])),
        rejected=rejected, mode=mode, calls=calls, cached_calls=cached,
        prompt_tokens=pt, completion_tokens=ct, seconds=round(time.perf_counter() - start, 3),
        api_seconds=round(api_seconds, 3),
    )
