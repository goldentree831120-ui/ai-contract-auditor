"""Groq chat-completions client with hard spending caps, pacing and a response cache.

Safety properties (each is unit-tested in tests/test_llm.py):
- Before every request, the worst case (estimated prompt tokens + max completion
  tokens) is checked against a daily token cap and a total USD cap. If either would
  be exceeded, BudgetExceeded is raised and nothing is sent.
- Requests are paced under per-minute request and token limits; HTTP 429 responses
  are retried after the server's retry-after delay.
- Identical requests are answered from .cache/llm/, so reruns cost nothing.
- The API key is read from the environment or .env and never printed or stored.

On Groq's Free plan nothing is billed: requests over a limit get HTTP 429. The USD cap
uses Groq's published paid-tier price so the code stays safe if the account is ever
upgraded to the paid Developer plan.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from auditor.dataset import REPO_ROOT
from auditor.env import setting

API_URL = "https://api.groq.com/openai/v1/chat/completions"
CACHE_DIR = REPO_ROOT / ".cache" / "llm"
LEDGER = REPO_ROOT / ".cache" / "llm_ledger.json"

DEFAULT_MODEL = "openai/gpt-oss-120b"
# USD per 1M tokens on Groq's paid Developer plan (console.groq.com/docs/models).
PRICES = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
}


class BudgetExceeded(RuntimeError):
    """Raised before a request that could push usage past a configured cap."""


class LLMError(RuntimeError):
    pass


def estimate_tokens(text: str) -> int:
    """Rough upper-leaning estimate (about 3.5 characters per token for code)."""
    return int(len(text) / 3.5) + 1


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = PRICES.get(model, (1.0, 4.0))  # unknown model: assume expensive
    return (prompt_tokens * pin + completion_tokens * pout) / 1_000_000


@dataclass
class Limits:
    daily_tokens: int = 150_000      # Groq Free plan: 200K tokens/day for gpt-oss-120b
    total_usd: float = 0.50          # hard cap at paid-tier prices
    tokens_per_minute: int = 7_000   # Free plan: 8K TPM
    requests_per_minute: int = 25    # Free plan: 30 RPM
    max_completion_tokens: int = 4_096

    @classmethod
    def from_settings(cls) -> "Limits":
        return cls(
            daily_tokens=int(setting("LLM_MAX_TOKENS_PER_DAY", "150000")),
            total_usd=float(setting("LLM_MAX_USD_TOTAL", "0.50")),
            tokens_per_minute=int(setting("LLM_TOKENS_PER_MINUTE", "7000")),
            requests_per_minute=int(setting("LLM_REQUESTS_PER_MINUTE", "25")),
            max_completion_tokens=int(setting("LLM_MAX_COMPLETION_TOKENS", "4096")),
        )


@dataclass
class Ledger:
    """Persistent usage record (in .cache/, git-ignored)."""

    path: Path = LEDGER
    data: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        self.data.setdefault("days", {})
        self.data.setdefault("total_usd", 0.0)
        self.data.setdefault("total_tokens", 0)

    @staticmethod
    def today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def tokens_today(self) -> int:
        return self.data["days"].get(self.today(), 0)

    def add(self, tokens: int, usd: float) -> None:
        day = self.today()
        self.data["days"][day] = self.data["days"].get(day, 0) + tokens
        self.data["total_tokens"] += tokens
        self.data["total_usd"] = round(self.data["total_usd"] + usd, 6)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))


Transport = Callable[[str, dict, dict], tuple[int, dict, dict]]


def http_transport(url: str, headers: dict, body: dict) -> tuple[int, dict, dict]:
    """POST JSON; returns (status, response headers, parsed body)."""
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers), json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            parsed = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            parsed = {"error": {"message": raw[:300].decode(errors="replace")}}
        return e.code, dict(e.headers or {}), parsed


class GroqClient:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        limits: Limits | None = None,
        ledger: Ledger | None = None,
        transport: Transport = http_transport,
        cache_dir: Path = CACHE_DIR,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        api_key: str | None = None,
    ):
        self.model = model
        self.limits = limits or Limits.from_settings()
        self.ledger = ledger or Ledger()
        self.transport = transport
        self.cache_dir = cache_dir
        self.sleep = sleep
        self.clock = clock
        self._api_key = api_key
        self._window: list[tuple[float, int]] = []  # (time, tokens) of recent requests

    def _key(self) -> str:
        key = self._api_key or setting("GROQ_API_KEY")
        if not key:
            raise LLMError("GROQ_API_KEY is not set. Put it in .env (see .env.example).")
        return key

    def _pace(self, projected: int) -> None:
        while True:
            now = self.clock()
            self._window = [(t, n) for t, n in self._window if now - t < 60]
            used = sum(n for _, n in self._window)
            if (len(self._window) < self.limits.requests_per_minute
                    and used + projected <= self.limits.tokens_per_minute) or not self._window:
                return
            self.sleep(max(0.5, 60 - (now - self._window[0][0]) + 0.1))

    def _check_budget(self, projected_tokens: int, projected_usd: float) -> None:
        if self.ledger.tokens_today() + projected_tokens > self.limits.daily_tokens:
            raise BudgetExceeded(
                f"daily token cap: {self.ledger.tokens_today()} used today (UTC) + up to "
                f"{projected_tokens} for this request > {self.limits.daily_tokens}. "
                "Rerun after 00:00 UTC (05:30 IST); finished contracts are cached and skipped."
            )
        if self.ledger.data["total_usd"] + projected_usd > self.limits.total_usd:
            raise BudgetExceeded(
                f"USD cap: ${self.ledger.data['total_usd']:.4f} so far + up to ${projected_usd:.4f} "
                f"> ${self.limits.total_usd:.2f} (paid-tier prices; Free plan is not billed)."
            )

    def complete_json(self, system: str, user: str, schema: dict, schema_name: str = "audit",
                      reasoning_effort: str = "low", repeat: int = 0) -> dict:
        """Return {"content": parsed JSON, "usage": {...}, "cached": bool, "seconds": float}."""
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_completion_tokens": self.limits.max_completion_tokens,
            "reasoning_effort": reasoning_effort,
            "include_reasoning": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        # `repeat` only changes the cache key (never the request), so repeat runs of the same
        # prompt are fresh samples; repeat 0 keeps the original key and reuses earlier runs.
        key = body if repeat == 0 else {**body, "_repeat": repeat}
        digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
        cache_file = self.cache_dir / f"{digest}.json"
        if cache_file.exists():
            hit = json.loads(cache_file.read_text())
            return {**hit, "cached": True}

        prompt_est = estimate_tokens(system + user)
        projected = prompt_est + self.limits.max_completion_tokens
        self._check_budget(projected, cost_usd(self.model, prompt_est, self.limits.max_completion_tokens))

        headers = {
            "Authorization": f"Bearer {self._key()}",
            "Content-Type": "application/json",
            "User-Agent": "ai-contract-auditor/0.1",
        }
        delay = 5.0
        for attempt in range(7):
            self._pace(projected)
            start = time.perf_counter()
            status, resp_headers, data = self.transport(API_URL, headers, body)
            seconds = time.perf_counter() - start
            if status == 200:
                break
            if status == 429 or status >= 500:
                retry_after = resp_headers.get("retry-after") or resp_headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay
                self.sleep(min(wait, 120))
                delay = min(delay * 2, 120)
                continue
            msg = (data.get("error") or {}).get("message", "")
            if status == 401:
                raise LLMError("Groq rejected the API key (HTTP 401). Check GROQ_API_KEY in .env.")
            raise LLMError(f"Groq HTTP {status}: {msg[:300]}")
        else:
            raise LLMError("Groq kept returning 429/5xx after 7 attempts; try again later.")

        usage = data.get("usage") or {}
        pt, ct = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        self._window.append((self.clock(), pt + ct))
        self.ledger.add(pt + ct, cost_usd(self.model, pt, ct))

        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        try:
            content = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"model returned non-JSON content: {text[:200]!r}") from exc
        result = {
            "content": content,
            "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct},
            "seconds": round(seconds, 3),
            "model": data.get("model", self.model),
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(result, indent=1))
        return {**result, "cached": False}
