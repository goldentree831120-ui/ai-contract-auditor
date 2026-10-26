# AI Smart-Contract Auditor (evaluated honestly)

An LLM-based Solidity auditor that reports findings as structured JSON (class, location,
reasoning, confidence), compared against the Slither static analyzer on a labeled dataset.
The point of the project is the evaluation: every number in this README comes from the
scripts in this repo, with the hardware noted, including the weak ones.

## Status

| milestone | what | status |
|---|---|---|
| M1 | labeled dataset (49 contracts, 9 classes) with provenance and licenses | done |
| M2 | Slither baseline, findings per contract | done |
| M3 | LLM agent with structured output and function-level slicing | done |
| M4 | RAG over SWC descriptions; ablation (LLM, +Slither, +RAG, both) | done |
| M5 | precision, recall, F1 per class, false-positive analysis, cost and time | planned |
| M6 | CLI, small UI, methodology and limitations write-up | planned |

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,slither]"
.venv/bin/pytest -q                                  # unit tests + dataset validation
.venv/bin/python scripts/validate_dataset.py         # dataset summary
.venv/bin/python scripts/build_dataset.py --check    # rebuild from pinned sources and compare
.venv/bin/python scripts/run_slither.py              # M2 baseline -> results/slither/
.venv/bin/python scripts/run_llm.py --dry-run         # M3 cost preview, no key needed
.venv/bin/python scripts/run_llm.py                   # M3 LLM run -> results/llm/llm_only/ (needs .env)
.venv/bin/python scripts/build_kb.py --check          # M4 knowledge base matches pinned SWC
.venv/bin/python scripts/eval_retrieval.py            # M4 retriever quality, no API calls
.venv/bin/python scripts/run_llm.py --context slither # M4 ablation runs: slither | rag | both
.venv/bin/python scripts/ablation.py                  # M4 table -> results/ablation/ABLATION.md
```

`--check` needs network access to github.com (it fetches the pinned source commits into
`.cache/`, which is git-ignored).

## Dataset (M1)

49 contracts: 31 vulnerable, 18 clean, 35 labeled findings across 9 DASP-style classes.
Clean contracts include the sources' own fixed versions of vulnerable samples and 5 hard
negatives (code that looks dangerous but is not exploitable). Contracts are sanitized so a
model cannot read the label from comments, file names or identifiers. Details, labeling
rules, exclusions and limitations: [dataset/README.md](dataset/README.md).

## Slither baseline (M2)

`scripts/run_slither.py` runs [Slither](https://github.com/crytic/slither) 0.11.6 on every
contract with its pinned solc version and writes per-contract findings, timing and the
machine it ran on to [results/slither/](results/slither/SUMMARY.md).

How findings are counted:

- Each Slither detector is mapped to at most one dataset class in
  [src/auditor/slither_map.py](src/auditor/slither_map.py). The mapping follows Slither's
  detector documentation and was fixed before looking at results.
- Detectors with no matching class (style, gas, compiler version, informational) are kept
  but reported as "unmapped", to show how much output a user must triage.
- Slither 0.11.6 has no detector for integer overflow or transaction ordering, so its
  recall on `arithmetic` and `front_running` is zero by construction.
- Benign reentrancy variants (`reentrancy-benign`, `reentrancy-events`,
  `reentrancy-unlimited-gas`) are not counted as reentrancy.

Compilers are not taken from the system: `src/auditor/solc.py` downloads the official
`solc-static-linux` release assets from GitHub and checks each against a pinned sha256.
`python -m auditor.solc` also reports whether each pin matches soliditylang.org's list.

Precision, recall and F1 per class come in M5, from these same result files.

## LLM agent (M3)

`scripts/run_llm.py` sends each sanitized contract, with line numbers, to
`openai/gpt-oss-120b` on Groq and asks for strict JSON: a list of findings, each with
`class` (one of the 9 dataset classes), `function`, `line`, `reasoning` and `confidence`.
The prompt contains no file name, label or source hint, and says that clean contracts are
common and an empty list is a valid answer. Settings: temperature 0, `reasoning_effort`
low, reasoning text not returned.

Every response is validated locally even though strict schema mode is on: unknown
classes and out-of-range lines are rejected and counted, confidence is clamped to 0..1,
and the function is re-derived from the line number (`function_from_line`) so location
scoring in M5 does not trust the model's own function label.

**Function-level slicing.** Contracts longer than 150 lines are audited one function at a
time. Each slice keeps every contract-level line, the signature of every other function
and one full function body, with original line numbers; findings outside the shown body
are rejected and the rest are merged per (class, function). No contract in this dataset
is longer than 87 lines, so the reported run uses whole-contract mode; slicing is covered
by unit tests and the `--slice-threshold` flag.

**Cost controls** (`src/auditor/llm.py`, all unit-tested):

| control | default | where |
|---|---|---|
| daily token cap, checked before each request using its worst case | 150,000 | `LLM_MAX_TOKENS_PER_DAY` |
| total USD cap at Groq's paid-tier price | $0.50 | `LLM_MAX_USD_TOTAL` |
| pacing under per-minute limits | 7,000 tokens, 25 requests | `LLM_TOKENS_PER_MINUTE`, `LLM_REQUESTS_PER_MINUTE` |
| max output tokens per request | 4,096 | `LLM_MAX_COMPLETION_TOKENS` |
| on-disk response cache (reruns are free) | `.cache/llm/` | git-ignored |

On Groq's Free plan nothing is billed; requests over a limit are refused. When a cap is
reached the run stops, saves what it has and exits with code 2; rerunning continues from
the cache. The API key is read from `.env` (git-ignored, template in `.env.example`) and is
never printed or written to results.

Results: [results/llm/llm_only/SUMMARY.md](results/llm/llm_only/SUMMARY.md). Precision,
recall and F1 per class come in M5.

## Retrieval and ablation (M4)

**Knowledge base** (`knowledge/swc_kb.json`, built by `scripts/build_kb.py` from the pinned
SWC commit): the Title, Description and Remediation prose of each SWC entry. The Samples
section, references and all code are dropped, because the dataset's contracts come from
those samples. Tests check that no dataset code line of 20+ characters and no sample file
name appears in the knowledge base.

**Retriever** (`src/auditor/kb.py`): BM25 in pure Python (no embedding API, no extra cost),
query = the contract's code, top 3 entries, each cut to 220 words.
`scripts/eval_retrieval.py` measures it without any API call: is a labeled SWC entry among
the top 3 for each vulnerable contract?

| knowledge base | entries | labeled SWC in top 3 | labeled class in top 3 |
|---|---|---|---|
| all SWC entries (first design) | 37 | 9/31 | 14/31 |
| taxonomy entries only (used) | 17 | 15/31 | 20/31 |

The first design retrieved generic entries (for example "code with no effects") for most
contracts. It was changed once, to keep only the 17 entries that map to the 9 classes the
model can output, and then not tuned further. That decision was made after seeing the first
number on the same 31 contracts, so the second number is optimistic. Keyword retrieval from
code to prose is weak either way: for the reentrancy contract c17 it returns delegatecall,
front-running and tx.origin entries.

**Ablation**: four LLM conditions on the same 49 contracts with the same model, system
prompt, schema and settings; only the context added before the code differs. The
no-context prompt is byte-identical to M3's, so the M3 run is reused as "LLM only".

| condition | added context |
|---|---|
| LLM only | none |
| LLM + Slither | Slither results of Low impact or above (Informational and Optimization dropped; rule fixed before any run), file names hidden |
| LLM + RAG | top 3 retrieved SWC passages |
| LLM + RAG + Slither | both |

Results: [results/ablation/ABLATION.md](results/ablation/ABLATION.md) and
[results/retrieval/SUMMARY.md](results/retrieval/SUMMARY.md).

## Sources

| source | license (checked) | used for | used in |
|---|---|---|---|
| [SWC-registry](https://github.com/SmartContractSecurity/SWC-registry) @ `1b62270` | MIT | 41 contracts and their labels | M1 |
| [sigp/solidity-security-blog](https://github.com/sigp/solidity-security-blog) @ `a412a46` | CC BY 4.0 | 7 contracts (modified, attributed) | M1 |
| [trailofbits/not-so-smart-contracts](https://github.com/trailofbits/not-so-smart-contracts) @ `020dbdb` | Apache-2.0 | 1 contract (modified, changes listed) | M1 |
| [smartbugs/smartbugs-curated](https://github.com/smartbugs/smartbugs-curated) @ `230e649` | Apache-2.0 repo; contracts keep their original licenses | label cross-check only; no files redistributed | M1 |
| [SunWeb3Sec/DeFiHackLabs](https://github.com/SunWeb3Sec/DeFiHackLabs) | Apache-2.0 (LICENSE file) | not used: holds attack PoCs, not the victim contracts | none |
| SWC-registry entry text (same commit as above) | MIT | knowledge base: Title, Description, Remediation only | M4 |

LLM: `openai/gpt-oss-120b` (open-weight model, Apache-2.0) served by
[Groq](https://console.groq.com) under Groq's terms of service; only the public dataset
contracts are sent.

Tools: [Slither](https://github.com/crytic/slither) 0.11.6 (AGPL-3.0) is run as an
unmodified external program and is not redistributed; solc binaries come from
[ethereum/solidity releases](https://github.com/ethereum/solidity/releases) (GPL-3.0) and are
downloaded at run time, not committed.

Upstream origins credited inside some SWC samples, and their license status, are listed in
[dataset/README.md](dataset/README.md#licensing-of-the-contracts).

## Repository layout

```
dataset/        spec.toml (labeling decisions), contracts/, labels.json, licenses/, raw/
knowledge/      swc_kb.json (M4 knowledge base, text only)
results/        slither/ (M2), llm/<run>/ (M3, M4), retrieval/, ablation/ (M4); results/raw/ is git-ignored
scripts/        build_dataset.py, validate_dataset.py, run_slither.py, run_llm.py,
                build_kb.py, eval_retrieval.py, ablation.py
src/auditor/    solidity.py, dataset.py, solc.py (pinned compilers),
                slither_map.py, slither_runner.py (M2),
                llm.py (Groq client, caps, cache), agent.py (prompt, schema, slicing), report.py,
                kb.py (knowledge base, BM25), context.py (Slither/RAG prompt context), sources.py
tests/          unit tests and dataset checks (run in CI)
```

## Limitations (so far)

- The contracts are short teaching samples in old Solidity (47 of 49 use 0.4.x). Results
  will not transfer to real DeFi protocols.
- Per-class counts are small (2 to 8 contracts), so per-class metrics will be indicative.
- These public samples are probably in LLM training data; sanitization limits answer lookup
  but not memorization.
- LLM output is not fully deterministic even at temperature 0, and the hosted model can
  change. Committed results record the model, prompt version and date; reruns may differ.
- Only one model and one prompt are evaluated; no prompt tuning was done on this dataset.

## Safety

Local analysis only. Nothing in this project deploys contracts, sends transactions or
touches mainnet. All contracts are public teaching samples; no claims are made about live
protocols.

## License

Code: MIT (see [LICENSE](LICENSE)). Dataset contracts keep their source licenses; see
[dataset/README.md](dataset/README.md#licensing-of-the-contracts).
