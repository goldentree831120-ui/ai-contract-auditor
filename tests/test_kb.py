import json

import pytest

from auditor.dataset import DATASET_DIR, load_labels, load_taxonomy
from auditor.kb import BM25, KB_FILE, load_kb, parse_entry, passage, taxonomy_entries, tokenize
from auditor.solidity import squash


def kb_text():
    return " ".join(f"{e['title']} {e['description']} {e['remediation']}" for e in load_kb())


def test_kb_has_no_code_blocks_or_sample_files():
    raw = KB_FILE.read_text()
    assert "```" not in raw
    samples = {e["source"]["path"].split("#")[-1] for e in load_labels() if "#" in e["source"]["path"]}
    for name in samples:
        assert name not in raw, name


def test_no_dataset_code_line_appears_in_kb():
    text = squash(kb_text())
    for e in load_labels():
        for line in (DATASET_DIR / e["file"]).read_text().split("\n"):
            s = squash(line)
            if len(s) >= 20:
                assert s not in text, (e["id"], line)


def test_parse_entry_drops_samples_and_links():
    md = ("# Title\n\nThing\n\n## Description\n\nSee [docs](http://x).\n\n```solidity\ncode();\n```\n\n"
          "## Remediation\n\nFix it.\n\n## Samples\n\n### a.sol\n\n```solidity\nsecret();\n```\n")
    e = parse_entry("SWC-999", md)
    assert e["title"] == "Thing" and e["description"] == "See docs." and e["remediation"] == "Fix it."
    assert "secret" not in json.dumps(e) and "code()" not in json.dumps(e)


def test_taxonomy_entries_match_taxonomy():
    ids = {e["id"] for e in taxonomy_entries()}
    mapped = {s for c in load_taxonomy()["classes"].values() for s in c["swc"]}
    assert ids == mapped and len(ids) == 17


def test_tokenize_splits_camel_case_and_normalizes():
    assert tokenize("txOrigin now suicide") == ["tx", "origin", "timestamp", "selfdestruct"]


@pytest.mark.parametrize("query,expected", [
    ("require(tx.origin == owner);", "SWC-115"),
    ("callee.delegatecall(data)", "SWC-112"),
])
def test_bm25_obvious_queries(query, expected):
    top = BM25(taxonomy_entries()).top(query, 1)
    assert top and top[0][0]["id"] == expected


def test_passage_is_bounded():
    e = max(load_kb(), key=lambda x: len(x["description"]))
    assert len(passage(e, words=50).split()) <= 50 + 6
