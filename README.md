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
| M3 | LLM agent with structured output and function-level slicing | planned |
| M4 | RAG over SWC descriptions; ablation (LLM, +Slither, +RAG, both) | planned |
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

## Sources

| source | license (checked) | used for | used in |
|---|---|---|---|
| [SWC-registry](https://github.com/SmartContractSecurity/SWC-registry) @ `1b62270` | MIT | 41 contracts and their labels | M1 |
| [sigp/solidity-security-blog](https://github.com/sigp/solidity-security-blog) @ `a412a46` | CC BY 4.0 | 7 contracts (modified, attributed) | M1 |
| [trailofbits/not-so-smart-contracts](https://github.com/trailofbits/not-so-smart-contracts) @ `020dbdb` | Apache-2.0 | 1 contract (modified, changes listed) | M1 |
| [smartbugs/smartbugs-curated](https://github.com/smartbugs/smartbugs-curated) @ `230e649` | Apache-2.0 repo; contracts keep their original licenses | label cross-check only; no files redistributed | M1 |
| [SunWeb3Sec/DeFiHackLabs](https://github.com/SunWeb3Sec/DeFiHackLabs) | Apache-2.0 (LICENSE file) | not used: holds attack PoCs, not the victim contracts | none |

Tools: [Slither](https://github.com/crytic/slither) 0.11.6 (AGPL-3.0) is run as an
unmodified external program and is not redistributed; solc binaries come from
[ethereum/solidity releases](https://github.com/ethereum/solidity/releases) (GPL-3.0) and are
downloaded at run time, not committed.

Upstream origins credited inside some SWC samples, and their license status, are listed in
[dataset/README.md](dataset/README.md#licensing-of-the-contracts).

## Repository layout

```
dataset/        spec.toml (labeling decisions), contracts/, labels.json, licenses/, raw/
results/        slither/ (M2 outputs; results/raw/ is git-ignored)
scripts/        build_dataset.py, validate_dataset.py, run_slither.py
src/auditor/    solidity.py, dataset.py, solc.py (pinned compilers),
                slither_map.py (detector -> class), slither_runner.py
tests/          unit tests and dataset checks (run in CI)
```

## Limitations (so far)

- The contracts are short teaching samples in old Solidity (47 of 49 use 0.4.x). Results
  will not transfer to real DeFi protocols.
- Per-class counts are small (2 to 8 contracts), so per-class metrics will be indicative.
- These public samples are probably in LLM training data; sanitization limits answer lookup
  but not memorization.

## Safety

Local analysis only. Nothing in this project deploys contracts, sends transactions or
touches mainnet. All contracts are public teaching samples; no claims are made about live
protocols.

## License

Code: MIT (see [LICENSE](LICENSE)). Dataset contracts keep their source licenses; see
[dataset/README.md](dataset/README.md#licensing-of-the-contracts).
