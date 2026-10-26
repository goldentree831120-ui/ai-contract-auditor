import json

import pytest

import auditor.context as ctx
from auditor.agent import user_prompt

SRC = "pragma solidity ^0.4.24;\ncontract A {\n    function f() public { tx.origin; }\n}\n"


def write_slither(tmp_path, findings):
    (tmp_path / "c07.json").write_text(json.dumps({"findings": findings}))


def test_slither_context_filters_impact_and_hides_file_names(tmp_path, monkeypatch):
    monkeypatch.setattr(ctx, "SLITHER_DIR", tmp_path)
    write_slither(tmp_path, [
        {"check": "tx-origin", "impact": "Medium", "confidence": "Medium",
         "description": "A.f() (dataset/contracts/c07.sol#3) uses tx.origin", "lines": [3]},
        {"check": "solc-version", "impact": "Informational", "confidence": "High",
         "description": "old compiler", "lines": [1]},
    ])
    out = ctx.slither_context("c07")
    assert "tx-origin" in out and "solc-version" not in out
    assert "c07" not in out and "contract.sol#3" in out


def test_slither_context_says_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ctx, "SLITHER_DIR", tmp_path)
    write_slither(tmp_path, [])
    assert "no findings" in ctx.slither_context("c07")


def test_missing_slither_results_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(ctx, "SLITHER_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        ctx.slither_context("c99")


def test_build_context_kinds(tmp_path, monkeypatch):
    monkeypatch.setattr(ctx, "SLITHER_DIR", tmp_path)
    write_slither(tmp_path, [])
    assert ctx.build_context("none", "c07", SRC) is None
    assert "Reference notes" in ctx.build_context("rag", "c07", SRC)
    both = ctx.build_context("both", "c07", SRC)
    assert "Reference notes" in both and "Static analyzer" in both
    with pytest.raises(ValueError):
        ctx.build_context("bogus", "c07", SRC)


def test_context_goes_before_code_and_no_context_is_unchanged():
    plain = user_prompt(SRC)
    assert plain.startswith("Audit this Solidity contract.\n\n```solidity\n")
    withc = user_prompt(SRC, context="NOTES")
    assert withc.startswith("Audit this Solidity contract.\n\nNOTES\n\n```solidity\n")
    assert withc.replace("NOTES\n\n", "") == plain
