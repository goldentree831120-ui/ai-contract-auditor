import json

import pytest

import auditor.cli as cli
from auditor.dataset import REPO_ROOT
from auditor.llm import GroqClient, Ledger, Limits

EXAMPLE = REPO_ROOT / "examples" / "TipJar.sol"


@pytest.mark.parametrize("pragma,expected", [
    ("pragma solidity ^0.4.24;", "0.4.26"),
    ("pragma solidity 0.4.25;", "0.4.25"),
    ("pragma solidity ^0.5.0;", "0.5.17"),
    ("pragma solidity >=0.4.22 <0.4.26;", "0.4.25"),
])
def test_pick_solc(pragma, expected):
    assert cli.pick_solc(pragma + "\ncontract A {}") == expected


def test_pick_solc_rejects_unpinned():
    with pytest.raises(cli.InputError, match="not pinned"):
        cli.pick_solc("pragma solidity ^0.8.20;\ncontract A {}")
    with pytest.raises(cli.InputError, match="no `pragma"):
        cli.pick_solc("contract A {}")


def test_dry_run_sends_nothing(capsys):
    assert cli.main(["audit", str(EXAMPLE), "--dry-run"]) == 0
    assert "estimated prompt tokens" in capsys.readouterr().out


def test_bad_input_exit_code(tmp_path, capsys):
    assert cli.main(["audit", str(tmp_path / "missing.sol")]) == 3
    (tmp_path / "x.txt").write_text("hello")
    assert cli.main(["audit", str(tmp_path / "x.txt")]) == 3


def fake_client_factory(tmp_path, findings):
    def transport(url, headers, body):
        return 200, {}, {"choices": [{"message": {"content": json.dumps({"findings": findings})}}],
                         "usage": {"prompt_tokens": 700, "completion_tokens": 100}}

    def factory(model, limits):
        return GroqClient(model=model, limits=Limits(), ledger=Ledger(path=tmp_path / "l.json"),
                          transport=transport, cache_dir=tmp_path / "c", sleep=lambda s: None, api_key="k")
    return factory


def test_audit_json_and_markdown(tmp_path, monkeypatch, capsys):
    f = {"class": "reentrancy", "function": "refund", "line": 19, "reasoning": "call before reset", "confidence": 0.9}
    monkeypatch.setattr(cli, "GroqClient", fake_client_factory(tmp_path, [f]))
    assert cli.main(["audit", str(EXAMPLE), "--format", "json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["findings"][0]["function_from_line"] == "refund" and out["context"] == "none"
    assert cli.main(["audit", str(EXAMPLE), "--rag"]) == 0
    md = capsys.readouterr().out
    assert "| 19 | reentrancy | refund |" in md and "not verified vulnerabilities" in md


def test_api_failure_exit_code(tmp_path, monkeypatch, capsys):
    def factory(model, limits):
        return GroqClient(model=model, limits=Limits(daily_tokens=1), ledger=Ledger(path=tmp_path / "l.json"),
                          transport=lambda *a: None, cache_dir=tmp_path / "c", api_key="k")
    monkeypatch.setattr(cli, "GroqClient", factory)
    assert cli.main(["audit", str(EXAMPLE)]) == 2
    assert "STOPPED" in capsys.readouterr().err
