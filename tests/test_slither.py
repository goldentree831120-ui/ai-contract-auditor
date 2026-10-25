import pytest

from auditor.dataset import load_taxonomy
from auditor.slither_map import DETECTOR_TO_CLASS, NO_DETECTOR_FOR, map_detector
from auditor.slither_runner import parse_results
from auditor.solc import PINNED_SHA256

FAKE = {
    "success": True,
    "results": {
        "detectors": [
            {
                "check": "reentrancy-eth",
                "impact": "High",
                "confidence": "Medium",
                "description": "Reentrancy in Bank.withdraw() (x.sol#10-14):\n\tmore",
                "elements": [
                    {"type": "function", "name": "withdraw", "source_mapping": {"lines": [10, 11, 12, 13, 14]}},
                    {
                        "type": "node",
                        "name": "msg.sender.call.value(a)()",
                        "source_mapping": {"lines": [11]},
                        "type_specific_fields": {"parent": {"type": "function", "name": "withdraw"}},
                    },
                ],
            },
            {
                "check": "solc-version",
                "impact": "Informational",
                "confidence": "High",
                "description": "Pragma version ^0.4.24 is too old",
                "elements": [{"type": "pragma", "name": "^0.4.24", "source_mapping": {"lines": [1]}}],
            },
        ]
    },
}


def test_parse_results_prefers_node_lines_and_keeps_function():
    f1, f2 = parse_results(FAKE)
    assert f1["class"] == "reentrancy"
    assert f1["lines"] == [11]
    assert f1["functions"] == ["withdraw"]
    assert f1["description"].startswith("Reentrancy in Bank.withdraw()")
    assert f2["class"] is None and f2["lines"] == [1] and f2["functions"] == []


def test_parse_results_handles_empty_output():
    assert parse_results({}) == []
    assert parse_results({"success": True, "results": {}}) == []


def test_mapping_targets_are_dataset_classes():
    classes = set(load_taxonomy()["classes"])
    assert set(DETECTOR_TO_CLASS.values()) <= classes
    assert set(NO_DETECTOR_FOR) <= classes
    assert not set(NO_DETECTOR_FOR) & set(DETECTOR_TO_CLASS.values())


def test_benign_reentrancy_is_not_mapped():
    for check in ("reentrancy-benign", "reentrancy-events", "reentrancy-unlimited-gas"):
        assert map_detector(check) is None


def test_every_mapped_name_is_a_real_slither_detector():
    pytest.importorskip("slither")
    import inspect

    from slither.detectors import all_detectors
    from slither.detectors.abstract_detector import AbstractDetector

    real = {
        d.ARGUMENT
        for _, d in inspect.getmembers(all_detectors, inspect.isclass)
        if issubclass(d, AbstractDetector)
    }
    assert set(DETECTOR_TO_CLASS) <= real, set(DETECTOR_TO_CLASS) - real


def test_every_dataset_solc_version_is_pinned():
    from auditor.dataset import load_labels

    assert {e["solc_version"] for e in load_labels()} <= set(PINNED_SHA256)
