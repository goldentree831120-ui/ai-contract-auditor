# Evaluation dataset (M1)

49 small Solidity contracts with ground-truth labels, used to evaluate Slither and the
LLM auditor in later milestones. Every file is rebuilt from pinned upstream commits by
`scripts/build_dataset.py`; CI fails if the committed files drift from a fresh build.

## Composition

| | count |
|---|---|
| contracts | 49 (31 vulnerable, 18 clean) |
| labeled findings | 34 |
| contract length | 9 to 87 lines (median 20) |
| compiler versions | 0.4.24 (7), 0.4.25 (4), 0.4.26 (36), 0.5.17 (2) |

Contracts per class (a contract can have more than one class):

| class | contracts |
|---|---|
| access_control | 8 |
| arithmetic | 5 |
| bad_randomness | 4 |
| denial_of_service | 3 |
| front_running | 3 |
| reentrancy | 3 |
| time_manipulation | 3 |
| unchecked_low_level_calls | 2 |
| other | 2 |

Roles: 30 `vulnerable_sample`, 13 `fixed_sample` (the source's own fix of a vulnerable
sample in this set), 5 `negative_sample` (hard negatives that look dangerous but are not
exploitable), 1 `fixed_sample_residual` (see below).

The full per-contract table is in [CONTRACTS.md](CONTRACTS.md) (generated).

## Files

| path | what |
|---|---|
| `spec.toml` | every human labeling decision: sample, label, anchors, renames, notes |
| `taxonomy.json` | the 9 classes and the SWC IDs mapped to each |
| `contracts/cNN.sol` | sanitized contracts; the only files a model or tool is given |
| `labels.json` | ground truth: label, classes, findings (class, SWC, line, function), provenance |
| `raw/<key>.sol` | verbatim upstream text, for provenance only; never shown to a model |
| `licenses/` | each source repo's license file, copied verbatim |

## Labeling rules

1. **Labels are judged against all 9 classes**, not only the weakness a sample was written
   to show. "Clean" means no known issue in any class. Because of this, the SWC-109
   `crypto_roulette_fixed.sol` sample is labeled **vulnerable**: its storage-pointer bug is
   fixed, but its randomness still comes from block data.
2. **Location** is one line per finding, chosen by an anchor string in `spec.toml` that must
   match exactly one line. The enclosing function is derived automatically. Evaluation in
   M5 will score location at function level, since line choice is partly a matter of taste.
3. **Ambiguous samples are excluded** rather than guessed (see below).

## Sanitization (to stop label leakage)

Upstream samples carry the answer in comments ("Safe version", "// bad") and in names
(`withdrawBalance_fixed`, `IntegerOverflowMul`, `SimpleSuicide`). The build therefore:

- removes all comments, and drops lines that held only a comment;
- renames identifiers that reveal the label or class (each rename is listed in
  `spec.toml` and in `labels.json` under `modifications`);
- names files `c01.sol` to `c49.sol`, ordered by content hash, so ID order says nothing
  about the label;
- adds `pragma solidity ^0.4.24;` to the sigp blog snippets, which have no pragma.

The validator fails if any contract contains a comment or an identifier matching a leak
pattern (`fixed`, `safe`, `vuln`, `overflow`, `reentr`, `suicide`, `checked`, `dos`, ...),
or if two contracts are identical apart from whitespace.

Names were **not** changed where the bug depends on them (wrong-constructor-name samples,
old-style constructors), and neutral names that hint at a domain (`Roulette`, `Lotto`,
`TimeLock`) were kept because real contracts have such names too.

## Excluded samples and why

| sample | reason |
|---|---|
| SWC-107 `modifier_reentrancy.sol` and `_fixed` | the external call goes to a `Bank` the contract deploys itself, so an attacker cannot control it; not exploitable as written |
| SWC-120 `old_blockhash_fixed.sol` | the fix's own check `block - block.number < 256` underflows, so the "fixed" contract is itself broken |
| SWC-120 `guess_the_random_number_fixed.sol` | still blockhash-based and one shared guesser slot; label unclear |
| SWC-126 `relayer.sol` and `_fixed` | the fix ignores the call's return value and calls a mismatched signature; label unclear |
| SWC-118 `incorrect_constructor_name2_fixed.sol` | after sanitizing, identical to `incorrect_constructor_name1_fixed.sol` apart from one blank line |
| SWC-102, 103, 111, 131, 135 samples | compiler-version, pragma, deprecated-function and dead-code hygiene; not security vulnerabilities in this taxonomy |
| all other SWC samples | not selected: either outside the 9 classes or a class was already covered; the project scope caps the set at 50 |

## Cross-check against SmartBugs-curated

[SmartBugs-curated](https://github.com/smartbugs/smartbugs-curated) independently annotates
26 of these contracts. No SmartBugs files are redistributed here; its annotations are only
compared at build time (`smartbugs_crosscheck` in `labels.json`):

- 25 of 29 comparable findings sit on a line SmartBugs also marks;
- 28 of 29 sit in a function SmartBugs also marks.

The one function-level difference is the extra `bad_randomness` label on
`crypto_roulette.sol`, which SmartBugs does not annotate. Line-level differences are noted
per contract in `spec.toml`.

## Licensing of the contracts

| source | license | contracts | notes |
|---|---|---|---|
| [SWC-registry](https://github.com/SmartContractSecurity/SWC-registry) @ `1b62270` | MIT | 41 | samples embedded in `entries/docs/SWC-*.md` |
| [sigp/solidity-security-blog](https://github.com/sigp/solidity-security-blog) @ `a412a46` | CC BY 4.0 | 7 | modified (comments removed, pragma added, one rename); attribution: Adrian Manning / Sigma Prime |
| [trailofbits/not-so-smart-contracts](https://github.com/trailofbits/not-so-smart-contracts) @ `020dbdb` | Apache-2.0 | 1 | modified (comments removed, renames); changes listed in `labels.json` |

**To review (upstream origins):** some SWC-registry samples credit an earlier origin in their
header (`credited_origin` in `labels.json`). SWC-registry publishes them under its MIT
license; the original licenses of these upstream pages were not independently confirmed:
blockchain.unica.it Ethereum survey (2 contracts), ConsenSys smart-contract-best-practices
(3; the repo has no LICENSE file), thec00n/smart-contract-honeypots (2), capturetheether.com
(1). Origins with confirmed licenses: ConsenSys evm-analyzer-benchmark-suite (MIT),
trailofbits/not-so-smart-contracts (Apache-2.0), sigp/solidity-security-blog (CC BY 4.0).

## Known limitations

- **Toy contracts.** Samples are 9 to 87 lines, written to teach one weakness each. Results
  on this set will not transfer to real DeFi code (multi-file, proxies, price oracles,
  flash loans). Real exploited contracts (for example from DeFiHackLabs incidents) live on
  Etherscan under mixed or unknown licenses, so they are not included.
- **Small per-class counts** (2 to 8). Per-class metrics in M5 will be reported with their
  support counts and should be read as indicative, not statistically strong.
- **Old Solidity.** 47 of 49 contracts use 0.4.x, before built-in overflow checks (0.8).
- **Training-data contamination.** SWC-registry, the sigp blog and not-so-smart-contracts
  are widely copied online, so LLMs have likely seen them. Comment and name sanitization
  reduces direct answer lookup but cannot undo memorization of code shapes.
- **RAG leakage risk (M4).** The SWC registry is also the planned knowledge base. M4 must
  index only the SWC descriptions and remediation text, never the code samples, or the
  retrieval step would hand the model the answer.
- **One labeler.** Labels follow the upstream sources and were reviewed against SmartBugs
  where it overlaps, but were assigned by one person.
