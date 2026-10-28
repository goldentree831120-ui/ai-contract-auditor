import json

import pytest

from auditor.llm import BudgetExceeded, GroqClient, Ledger, Limits, LLMError, cost_usd

SCHEMA = {"type": "object", "properties": {"findings": {"type": "array"}},
          "required": ["findings"], "additionalProperties": False}


def ok_response(content, pt=100, ct=50):
    return 200, {}, {"model": "openai/gpt-oss-120b",
                     "choices": [{"message": {"content": json.dumps(content)}}],
                     "usage": {"prompt_tokens": pt, "completion_tokens": ct}}


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append((url, headers, body))
        return self.responses.pop(0)


def make_client(tmp_path, transport, **limits):
    return GroqClient(
        limits=Limits(**limits), ledger=Ledger(path=tmp_path / "ledger.json"),
        transport=transport, cache_dir=tmp_path / "cache", sleep=lambda s: None,
        clock=lambda: 0.0, api_key="test-key",
    )


def test_request_shape_and_parsing(tmp_path):
    t = FakeTransport([ok_response({"findings": []})])
    r = make_client(tmp_path, t).complete_json("sys", "user", SCHEMA)
    assert r["content"] == {"findings": []} and not r["cached"]
    assert r["usage"]["total_tokens"] == 150
    url, headers, body = t.calls[0]
    assert url.endswith("/openai/v1/chat/completions")
    assert headers["Authorization"] == "Bearer test-key"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["reasoning_effort"] == "low" and body["include_reasoning"] is False
    assert body["temperature"] == 0


def test_cache_hit_makes_no_second_call(tmp_path):
    t = FakeTransport([ok_response({"findings": []})])
    c = make_client(tmp_path, t)
    c.complete_json("s", "u", SCHEMA)
    again = c.complete_json("s", "u", SCHEMA)
    assert again["cached"] and len(t.calls) == 1


def test_ledger_records_usage(tmp_path):
    t = FakeTransport([ok_response({"findings": []}, pt=1000, ct=500)])
    c = make_client(tmp_path, t)
    c.complete_json("s", "u", SCHEMA)
    data = json.loads((tmp_path / "ledger.json").read_text())
    assert data["total_tokens"] == 1500
    assert data["total_usd"] == pytest.approx(cost_usd("openai/gpt-oss-120b", 1000, 500))


def test_daily_cap_blocks_before_sending(tmp_path):
    t = FakeTransport([])
    c = make_client(tmp_path, t, daily_tokens=1000, max_completion_tokens=4096)
    with pytest.raises(BudgetExceeded, match="daily token cap"):
        c.complete_json("s", "u", SCHEMA)
    assert t.calls == []


def test_usd_cap_blocks_before_sending(tmp_path):
    t = FakeTransport([])
    c = make_client(tmp_path, t, total_usd=0.0001)
    with pytest.raises(BudgetExceeded, match="USD cap"):
        c.complete_json("s", "u", SCHEMA)
    assert t.calls == []


def test_429_is_retried_with_retry_after(tmp_path):
    waits = []
    t = FakeTransport([(429, {"retry-after": "3"}, {}), ok_response({"findings": []})])
    c = make_client(tmp_path, t)
    c.sleep = waits.append
    c.complete_json("s", "u", SCHEMA)
    assert len(t.calls) == 2 and 3.0 in waits


def test_401_gives_clear_error_without_key(tmp_path):
    t = FakeTransport([(401, {}, {"error": {"message": "Invalid API Key"}})])
    with pytest.raises(LLMError) as exc:
        make_client(tmp_path, t).complete_json("s", "u", SCHEMA)
    assert "GROQ_API_KEY" in str(exc.value) and "test-key" not in str(exc.value)


def test_missing_key_is_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("auditor.llm.setting", lambda name, default=None: default)
    c = make_client(tmp_path, FakeTransport([]))
    c._api_key = None
    with pytest.raises(LLMError, match="GROQ_API_KEY is not set"):
        c.complete_json("s", "u", SCHEMA)


def test_non_json_content_is_an_error(tmp_path):
    bad = (200, {}, {"choices": [{"message": {"content": "not json"}}], "usage": {}})
    with pytest.raises(LLMError, match="non-JSON"):
        make_client(tmp_path, FakeTransport([bad])).complete_json("s", "u", SCHEMA)


def test_pacing_waits_when_minute_token_budget_is_used(tmp_path):
    now = [0.0]
    waits = []
    t = FakeTransport([ok_response({"findings": []}, pt=3000, ct=3000),
                       ok_response({"findings": []}, pt=10, ct=10)])
    c = make_client(tmp_path, t, tokens_per_minute=7000, max_completion_tokens=1000)
    c.clock = lambda: now[0]

    def sleep(s):
        waits.append(s)
        now[0] += s

    c.sleep = sleep
    c.complete_json("s", "first", SCHEMA)
    c.complete_json("s", "second", SCHEMA)
    assert waits and sum(waits) >= 59


def test_repeat_changes_cache_key_but_not_request(tmp_path):
    t = FakeTransport([ok_response({"findings": []}), ok_response({"findings": []})])
    c = make_client(tmp_path, t)
    c.complete_json("s", "u", SCHEMA)
    again = c.complete_json("s", "u", SCHEMA, repeat=1)
    assert not again["cached"] and len(t.calls) == 2
    assert t.calls[0][2] == t.calls[1][2]  # identical request body
    assert c.complete_json("s", "u", SCHEMA, repeat=1)["cached"]


def test_network_error_is_retried_then_reported(tmp_path):
    net = (0, {}, {"error": {"message": "network error: [Errno 101] Network is unreachable"}})
    t = FakeTransport([net, net, ok_response({"findings": []})])
    assert make_client(tmp_path, t).complete_json("s", "u", SCHEMA)["content"] == {"findings": []}
    assert len(t.calls) == 3
    t2 = FakeTransport([net] * 7)
    with pytest.raises(LLMError, match="network error"):
        make_client(tmp_path / "b", t2).complete_json("s", "u", SCHEMA)


def test_http_transport_turns_connection_failure_into_status_0(monkeypatch):
    import urllib.error

    from auditor import llm

    def boom(*a, **k):
        raise urllib.error.URLError(OSError(101, "Network is unreachable"))

    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    status, _, body = llm.http_transport("https://example.invalid", {}, {})
    assert status == 0 and "network error" in body["error"]["message"]
