import json

from auditor.dataset import (
    DATASET_DIR,
    MAX_CONTRACTS,
    MIN_CONTRACTS,
    leaked_identifiers,
    load_labels,
    load_taxonomy,
    summary,
    validate,
)


def test_dataset_is_valid():
    assert validate() == []


def test_size_and_balance():
    s = summary()
    assert MIN_CONTRACTS <= s["contracts"] <= MAX_CONTRACTS
    assert s["vulnerable"] > 0 and s["clean"] > 0


def test_every_class_has_at_least_two_contracts():
    s = summary()
    for c in load_taxonomy()["classes"]:
        assert s["per_class_contracts"].get(c, 0) >= 2, c


def test_findings_point_inside_functions():
    for e in load_labels():
        for f in e["findings"]:
            assert f["function"] != "<contract-level>", (e["id"], f)


def test_raw_provenance_and_licenses_present():
    for e in load_labels():
        assert (DATASET_DIR / "raw" / f"{e['key']}.sol").exists()
        assert (DATASET_DIR / e["source"]["license_file_in_repo"]).exists()
        assert e["source"]["commit"] in e["source"]["url"]


def test_leak_checker_catches_obvious_names():
    assert leaked_identifiers("contract Reentrance { function withdraw_fixed() {} }") == [
        "Reentrance",
        "withdraw_fixed",
    ]
    assert leaked_identifiers("contract Bank { function withdraw() { suicide(msg.sender); } }") == []


def test_labels_json_is_sorted_and_stable():
    data = json.loads((DATASET_DIR / "labels.json").read_text())
    ids = [e["id"] for e in data["contracts"]]
    assert ids == sorted(ids)
