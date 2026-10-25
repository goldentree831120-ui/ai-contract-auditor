"""Map Slither detector names to the dataset's vulnerability classes.

Only detectors whose documented purpose matches a class are mapped. Every other
detector (style, gas, compiler-version, informational) is kept in the results as
"unmapped": it does not count as a prediction for any class, but its volume is
reported so readers can see how much output a user would have to triage.

Decisions worth stating:
- reentrancy-benign, reentrancy-events and reentrancy-unlimited-gas are NOT mapped:
  Slither itself describes them as benign or as transfer/send-only (2300 gas), which
  is exactly the case our hard negatives test.
- costly-loop is NOT mapped to denial_of_service: Slither documents it as a gas
  optimization, not a DoS finding.
- Slither 0.11.6 has no detector for integer overflow (arithmetic), transaction
  ordering (front_running) or signature malleability. Its recall on those is 0 by
  construction, and the evaluation reports it that way.
"""

from __future__ import annotations

DETECTOR_TO_CLASS: dict[str, str] = {
    # access_control
    "suicidal": "access_control",
    "arbitrary-send-eth": "access_control",
    "arbitrary-send-erc20": "access_control",
    "arbitrary-send-erc20-permit": "access_control",
    "controlled-delegatecall": "access_control",
    "delegatecall-loop": "access_control",
    "controlled-array-length": "access_control",
    "tx-origin": "access_control",
    "unprotected-upgrade": "access_control",
    "protected-vars": "access_control",
    # reentrancy
    "reentrancy-eth": "reentrancy",
    "reentrancy-no-eth": "reentrancy",
    "reentrancy-balance": "reentrancy",
    # bad_randomness
    "weak-prng": "bad_randomness",
    # unchecked_low_level_calls
    "unchecked-lowlevel": "unchecked_low_level_calls",
    "unchecked-send": "unchecked_low_level_calls",
    "unchecked-transfer": "unchecked_low_level_calls",
    # denial_of_service
    "calls-loop": "denial_of_service",
    # time_manipulation
    "timestamp": "time_manipulation",
    # other
    "uninitialized-storage": "other",
}

NO_DETECTOR_FOR = ["arithmetic", "front_running"]


def map_detector(check: str) -> str | None:
    return DETECTOR_TO_CLASS.get(check)
