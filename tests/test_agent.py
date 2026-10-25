import json

from auditor.agent import (
    audit,
    make_slices,
    numbered,
    output_schema,
    system_prompt,
    user_prompt,
    validate_findings,
)
from auditor.dataset import DATASET_DIR, load_labels, load_taxonomy

SRC = """pragma solidity ^0.4.24;
contract Bank {
    mapping(address => uint) balances;
    function deposit() public payable {
        balances[msg.sender] += msg.value;
    }
    function withdraw() public {
        require(msg.sender.call.value(balances[msg.sender])());
        balances[msg.sender] = 0;
    }
}
"""


class StubClient:
    def __init__(self, findings_by_call):
        self.findings_by_call = list(findings_by_call)
        self.prompts = []

    def complete_json(self, system, user, schema, reasoning_effort="low"):
        self.prompts.append(user)
        return {"content": {"findings": self.findings_by_call.pop(0)}, "cached": False,
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}, "seconds": 0.1}


def test_schema_is_strict_compatible():
    s = output_schema()
    item = s["properties"]["findings"]["items"]
    assert s["additionalProperties"] is False and item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])
    assert set(item["properties"]["class"]["enum"]) == set(load_taxonomy()["classes"])


def test_prompts_contain_no_label_information():
    text = system_prompt() + user_prompt(SRC)
    for leak in ("vulnerable", "clean contract", "c01", "SWC-1", "label"):
        assert leak not in text


def test_every_dataset_prompt_hides_file_ids_and_keys():
    for e in load_labels():
        p = user_prompt((DATASET_DIR / e["file"]).read_text())
        assert e["id"] not in p and e["key"] not in p


def test_numbered_keeps_original_line_numbers():
    out = numbered(SRC, keep={1, 8})
    assert out.splitlines() == [" 1 | pragma solidity ^0.4.24;",
                                " 8 |         require(msg.sender.call.value(balances[msg.sender])());"]


def test_slices_keep_context_and_other_signatures():
    slices = dict(make_slices(SRC))
    assert set(slices) == {"deposit", "withdraw"}
    w = slices["withdraw"]
    assert {1, 2, 3, 4, 7, 8, 9, 10, 11} <= w and 5 not in w


def test_validate_rejects_bad_findings_and_derives_function():
    raw = [
        {"class": "reentrancy", "function": "withdraw", "line": 8, "reasoning": "r", "confidence": 1.4},
        {"class": "made_up", "function": "x", "line": 8, "reasoning": "r", "confidence": 0.5},
        {"class": "arithmetic", "function": "x", "line": 99, "reasoning": "r", "confidence": 0.5},
    ]
    kept, rejected = validate_findings(raw, SRC)
    assert len(kept) == 1 and len(rejected) == 2
    assert kept[0]["function_from_line"] == "withdraw" and kept[0]["confidence"] == 1.0


def test_audit_whole_mode_and_dedup():
    f = {"class": "reentrancy", "function": "withdraw", "line": 8, "reasoning": "r", "confidence": 0.6}
    g = dict(f, line=9, confidence=0.9)
    r = audit(SRC, StubClient([[f, g]]))
    assert r.mode == "whole" and r.calls == 1
    assert len(r.findings) == 1 and r.findings[0]["confidence"] == 0.9


def test_audit_sliced_mode_one_call_per_function():
    f = {"class": "reentrancy", "function": "withdraw", "line": 8, "reasoning": "r", "confidence": 0.8}
    outside = dict(f, line=5)  # line 5 is not shown in the withdraw slice
    client = StubClient([[], [f, outside]])
    r = audit(SRC, client, slice_threshold=5)
    assert r.mode == "sliced" and r.calls == 2
    assert [x["line"] for x in r.findings] == [8]
    assert len(r.rejected) == 1 and "not shown" in r.rejected[0]["reason"]
    assert "Audit the function `withdraw`" in client.prompts[1]


def test_schema_serializes():
    json.dumps(output_schema())
