# AI Smart-Contract Auditor, evaluated honestly

An LLM-based Solidity auditor (`openai/gpt-oss-120b` on Groq) that reports findings as
schema-checked JSON (class, function, line, reasoning, confidence), measured against the
Slither static analyzer on 49 labeled contracts. The point of the project is the
evaluation: every number below comes from the scripts and committed result files in this
repository, run on an Intel i5-10210U laptop (WSL Ubuntu), including the weak results.

**Results explorer:** https://goldentree831120-ui.github.io/ai-contract-auditor/
(per-class tables, every contract with its labels and each tool's findings, every false
positive). It is a single static page built from the committed results.

## Summary

- On 49 short labeled contracts, the LLM averaged **contract-level F1 0.61 over three runs**
  (0.64, 0.57, 0.61); Slither 0.11.6 reached **0.51**. Most of the gap comes from classes
  Slither has no detector for (integer overflow, front-running). The 95% intervals overlap.
- **Sending the identical request again changed the answer.** At temperature 0, repeat runs
  changed the predicted classes on about a third of contracts and moved F1 by up to 0.07.
- **Extra context gave no reliable gain.** Adding Slither's output, retrieved SWC notes, or
  both moved F1 by less than that run-to-run noise (three-run means: 0.61 without context,
  0.64 with both).
- The LLM reported issues on **4 to 9 of 18 clean contracts** per run. Every one is listed with
  the model's reasoning; the recurring causes are below.
- Five labeled issues were **missed by every tool and condition**, including signature
  malleability and two of the three front-running samples.

## Results

Single run per condition (the first run of each). Contract level = right class anywhere in
the contract; function level = right class in the right function; detection = vulnerable or
not. Intervals resample the 49 contracts (1,000 bootstrap draws).

| condition | contract P | contract R | contract F1 (95% CI) | function F1 | detection P / R | clean flagged |
|---|---|---|---|---|---|---|
| Slither 0.11.6 | 0.49 | 0.53 | 0.51 (0.37-0.63) | 0.43 | 0.74 / 0.65 | 7/18 |
| LLM only | 0.60 | 0.68 | 0.64 (0.52-0.75) | 0.56 | 0.81 / 0.84 | 6/18 |
| LLM + Slither | 0.54 | 0.68 | 0.60 (0.48-0.69) | 0.52 | 0.72 / 0.74 | 9/18 |
| LLM + RAG | 0.54 | 0.59 | 0.56 (0.44-0.68) | 0.55 | 0.75 / 0.77 | 8/18 |
| LLM + RAG + Slither | 0.62 | 0.62 | 0.62 (0.46-0.76) | 0.58 | 0.81 / 0.71 | 5/18 |

Run-to-run variance (identical requests, cache bypassed):

| condition | contract F1 per run | clean flagged per run | contracts with identical classes in all 3 runs |
|---|---|---|---|
| LLM only | 0.64, 0.57, 0.61 | 6, 8, 6 | 33/49 |
| LLM + RAG + Slither | 0.62, 0.65, 0.64 | 5, 7, 4 | 32/49 |

Cost and time per contract: Slither 0.82 s locally; the LLM about 1,000 to 1,600 tokens and
1.1 to 1.7 s median Groq round-trip across the 8 runs, $0 on Groq's free plan (about $0.013
to $0.017 for all 49 contracts at paid-tier prices). Full tables, per-class scores, every false positive and
the misses: [results/eval/RESULTS.md](results/eval/RESULTS.md).

### What the numbers support, and what they do not

- Every LLM condition scores above Slither at contract level, mostly because Slither has no
  detector for integer overflow or front-running. The intervals overlap, so even this gap
  is not established on 49 contracts.
- **No added context clearly helped.** The four LLM conditions differ by a few contracts,
  their intervals overlap almost completely, and run-to-run variance (see RESULTS.md) is of
  a similar size. Retrieval raised bad_randomness recall but added arithmetic false
  positives; Slither output raised false alarms on clean contracts (6 to 9).
- Function-level F1 is 0.01 to 0.08 below contract level: the tools sometimes name the
  right weakness in the wrong function.
- Five labeled issues were missed by every tool and condition: signature malleability
  (c14), two front-running cases (c29, c39), a block-number clock (c49) and a gas-limit
  DoS (c11). They are listed in RESULTS.md with the labeled function.
- Every false positive on a clean contract is listed in RESULTS.md with the model's
  reasoning. Recurring causes, read from that list:
  - the hard-negative proxy (c16), whose delegatecall can never persist state, is flagged
    by Slither and all four LLM conditions;
  - overflow warnings on `+= msg.value`, where wrapping would need more Ether than exists
    (c03, c48);
  - intentionally public functions or owner-set callees reported as missing access
    control (c01, c12, c15, c23, c45);
  - week-long time locks reported as timestamp manipulation, though miners can shift
    timestamps only by seconds (c34, c48); these appear only in conditions given Slither
    output or retrieved notes, matching Slither's own `timestamp` alerts;
  - with retrieval, an underflow the code can never reach (hard negative c30).

## Use it on a contract

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[slither]"
cp .env.example .env            # then put your Groq API key in .env (never commit it)
.venv/bin/auditor audit examples/TipJar.sol --dry-run          # token/cost estimate, sends nothing
.venv/bin/auditor audit examples/TipJar.sol                    # Markdown report
.venv/bin/auditor audit examples/TipJar.sol --slither --rag --format json
```

`--slither` picks a pinned, hash-checked solc version from the file's pragma (0.4.24 to
0.5.17 are pinned) and gives Slither's Low-or-higher findings to the model. Long files are
audited one function at a time. The same token and dollar caps as the benchmark apply.
Treat the output as leads to check by hand: on the benchmark this model flagged a third of
the clean contracts in a typical run.

## Reproduce the evaluation

```bash
.venv/bin/pip install -e ".[dev,slither]"
.venv/bin/pytest -q                                    # unit tests, dataset and report checks
.venv/bin/python scripts/build_dataset.py --check      # dataset rebuilds from pinned upstream commits
.venv/bin/python scripts/run_slither.py                # Slither baseline -> results/slither/
.venv/bin/python scripts/run_llm.py --dry-run          # cost preview for an LLM run, no key needed
.venv/bin/python scripts/run_llm.py --context none     # also: slither | rag | both; --repeat N for repeats
.venv/bin/python scripts/evaluate.py                   # all tables -> results/eval/RESULTS.md
.venv/bin/python scripts/build_site.py                 # results explorer -> site/index.html
```

LLM runs stop before any request that could exceed the daily token cap (150,000 by default,
under the free plan's 200,000) and resume from the on-disk cache. Reproducing all 8 committed
LLM runs takes about 510,000 tokens, roughly four days on the free plan. Re-running gives
different LLM numbers, as the variance table shows; the committed runs record model, prompt
version and date.

## Methodology

### Dataset

49 contracts: 31 vulnerable, 18 clean, 35 labeled findings across 9 DASP-style classes.
Clean contracts include the sources' own fixed versions of vulnerable samples and 5 hard
negatives (code that looks dangerous but is not exploitable). Contracts are sanitized so a
model cannot read the label from comments, file names or identifiers. Details, labeling
rules, exclusions and limitations: [dataset/README.md](dataset/README.md).

### Slither baseline

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

### LLM agent

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

### Retrieval and ablation

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

### Evaluation

`scripts/evaluate.py` computes everything from the committed result files with no API calls,
and CI fails if the committed report is out of date. Units are (contract, class) at contract
level and (contract, class, function) at function level; the LLM's function is derived from
its reported line, not taken from its own label. Precision is undefined when a tool never
reports a class, and recall and F1 are then 0, so a class a tool cannot detect counts
against it. Intervals are percentile bootstrap intervals over contracts. Repeat runs send
the byte-identical request with the cache bypassed.

## Limitations

- **Toy contracts.** 9 to 87 lines each, written to teach one weakness. Results will not
  transfer to real protocols (multi-file systems, proxies, oracles, flash loans, economic
  attacks). Real exploited contracts were left out because their licenses are unclear.
- **Old Solidity.** 47 of 49 contracts use 0.4.x, before built-in overflow checks (0.8).
  Arithmetic findings, the LLM's biggest advantage here, matter much less in modern code.
- **Small samples.** 49 contracts and 2 to 8 per class: intervals are about ±0.12 F1 and
  per-class scores are indicative only.
- **Training-data contamination.** The SWC registry, sigp blog and not-so-smart-contracts are
  widely copied online; the model has probably seen these samples. Comments and revealing
  names were removed, which limits answer lookup but not memorization.
- **Non-determinism.** Identical requests at temperature 0 gave different answers on a third
  of contracts. Only two conditions were repeated (three runs each); the other conditions
  have one run.
- **One model, one prompt, no tuning.** Other models or prompts may do better or worse; no
  prompt was adjusted on this dataset, so there is no held-out set either.
- **Labels.** Assigned by one person from the upstream sources, cross-checked against
  SmartBugs-curated where they overlap (29 of 30 findings in the same function); one label
  was revised during M2 and is disclosed in [dataset/README.md](dataset/README.md).
- **Weak retrieval.** Keyword (BM25) retrieval from code to prose found a labeled SWC entry in
  the top 3 for only 15 of 31 vulnerable contracts, so the RAG result says little about
  retrieval done well.
- **Slither mapping.** Slither detectors were mapped to classes by hand from its
  documentation; a different mapping changes its scores.

## Safety

Local analysis only. Nothing in this project deploys contracts, sends transactions or
touches mainnet. All contracts are public teaching samples; no claims are made about live
protocols.

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
examples/       TipJar.sol (a small contract written for trying the CLI)
results/        slither/, llm/<run>/ (incl. _r1/_r2 repeats), retrieval/, ablation/, eval/; results/raw/ is git-ignored
scripts/        build_dataset.py, validate_dataset.py, run_slither.py, run_llm.py,
                build_kb.py, eval_retrieval.py, ablation.py, evaluate.py,
                build_site.py + site_template.html (results explorer)
src/auditor/    solidity.py, dataset.py, solc.py (pinned compilers),
                slither_map.py, slither_runner.py (M2),
                llm.py (Groq client, caps, cache), agent.py (prompt, schema, slicing), report.py,
                kb.py (knowledge base, BM25), context.py (Slither/RAG prompt context), sources.py,
                metrics.py (precision/recall/F1, bootstrap intervals), cli.py (auditor command)
tests/          unit tests and dataset checks (run in CI)
```

## Project history

| milestone | what |
|---|---|
| M1 | labeled dataset (49 contracts, 9 classes) with provenance, licenses, leak checks |
| M2 | Slither 0.11.6 baseline with pinned compilers |
| M3 | LLM agent: strict JSON, local validation, function-level slicing, cost caps |
| M4 | text-only SWC knowledge base, BM25 retrieval, four-way ablation |
| M5 | per-class P/R/F1, bootstrap intervals, false-positive analysis, repeat runs |
| M6 | CLI, results explorer, this write-up |

## License

Code: MIT (see [LICENSE](LICENSE)). Dataset contracts keep their source licenses; see
[dataset/README.md](dataset/README.md#licensing-of-the-contracts).
