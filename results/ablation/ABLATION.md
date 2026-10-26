# Ablation (M4)

Contract level: a contract counts as flagged for a class if the tool reports that class anywhere in it. Hit = flagged on a contract that has the class; false alarm = flagged on one that does not. Same 49 contracts, model, prompt and settings in every LLM row; only the added context differs.

| condition | vulnerable flagged | clean flagged | tokens (prompt + completion) | tokens per contract |
|---|---|---|---|---|
| Slither 0.11.6 (M2) | 20/31 | 7/18 | n/a (local tool) | n/a |
| LLM only | 26/31 | 6/18 | 38267 + 11879 | 1023.4 |
| LLM + Slither | 23/31 | 9/18 | 42188 + 11902 | 1103.9 |
| LLM + RAG | 24/31 | 8/18 | 62275 + 10392 | 1483.0 |
| LLM + RAG + Slither | 22/31 | 5/18 | 66196 + 10633 | 1567.9 |

## Per class: hits / false alarms

| class | n | Slither 0.11.6 (M2) | LLM only | LLM + Slither | LLM + RAG | LLM + RAG + Slither |
|---|---|---|---|---|---|---|
| access_control | 8 | 6 / 12 | 6 / 7 | 6 / 9 | 6 / 7 | 6 / 4 |
| arithmetic | 5 | 0 / 0 | 5 / 4 | 4 / 2 | 4 / 7 | 5 / 4 |
| reentrancy | 3 | 3 / 0 | 3 / 0 | 3 / 1 | 3 / 0 | 2 / 0 |
| bad_randomness | 5 | 3 / 0 | 3 / 0 | 4 / 0 | 5 / 0 | 4 / 0 |
| unchecked_low_level_calls | 2 | 2 / 0 | 2 / 0 | 2 / 0 | 1 / 0 | 1 / 0 |
| denial_of_service | 3 | 1 / 0 | 1 / 1 | 1 / 1 | 0 / 1 | 1 / 1 |
| front_running | 3 | 0 / 0 | 1 / 2 | 0 / 1 | 0 / 0 | 0 / 1 |
| time_manipulation | 3 | 2 / 7 | 2 / 1 | 2 / 5 | 1 / 2 | 1 / 3 |
| other | 2 | 1 / 0 | 0 / 0 | 1 / 1 | 0 / 0 | 1 / 0 |
