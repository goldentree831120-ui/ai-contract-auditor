"""Knowledge base of SWC weakness descriptions, and a BM25 retriever over it.

Leakage rule: the dataset's contracts come from the same SWC registry, so the
knowledge base keeps only each entry's Title, Description and Remediation prose.
The Samples section (where every dataset contract came from), the References and
all fenced code are dropped, and tests check that no dataset code line appears in it.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from auditor.dataset import REPO_ROOT

KB_FILE = REPO_ROOT / "knowledge" / "swc_kb.json"
SWC = {"repo": "SmartContractSecurity/SWC-registry", "commit": "1b6227074ecd180b374e4844153afdda0332f979"}
PASSAGE_WORDS = 220  # each retrieved entry is cut to this many words in the prompt

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def _section(md: str, name: str) -> str:
    m = re.search(rf"^##\s+{name}\s*\n(.*?)(?=^##\s|\Z)", md, re.M | re.S)
    return m.group(1).strip() if m else ""


def _clean(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)  # drop any fenced code
    text = _LINK.sub(r"\1", text)                       # keep link text, drop URL
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_entry(swc_id: str, md: str) -> dict:
    title = re.search(r"^# Title\s*\n+(.+)$", md, re.M)
    return {
        "id": swc_id,
        "title": title.group(1).strip() if title else swc_id,
        "description": _clean(_section(md, "Description")),
        "remediation": _clean(_section(md, "Remediation")),
    }


def build_entries(swc_root: Path) -> list[dict]:
    docs = sorted((swc_root / "entries" / "docs").glob("SWC-*.md"))
    return [parse_entry(p.stem, p.read_text()) for p in docs]


def load_kb(path: Path = KB_FILE) -> list[dict]:
    return json.loads(path.read_text())["entries"]


# ---------------------------------------------------------------- retrieval

_STOP = set("""a an and are as at be been but by can could do does for from has have if in into is it
its may might more most must no not of on or other our should so such than that the their them then
there these they this those to too was we were what when which while will with would you your also
using use used uses any all each one two only same very function public private internal external
returns return view pure payable uint uint256 uint8 address bool bytes bytes32 string
mapping contract pragma solidity true false new emit event""".split())

# Neutral spelling normalizations between old Solidity and prose (no class words added).
_NORMALIZE = {"now": "timestamp", "suicide": "selfdestruct", "sha3": "keccak256", "throw": "revert"}


def tokenize(text: str) -> list[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)  # split camelCase
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9]*", text.lower())
    out = []
    for w in words:
        w = _NORMALIZE.get(w, w)
        if len(w) > 1 and w not in _STOP:
            out.append(w)
    return out


class BM25:
    def __init__(self, entries: list[dict], k1: float = 1.5, b: float = 0.75):
        self.entries = entries
        self.docs = [tokenize(f"{e['title']} {e['title']} {e['description']} {e['remediation']}")
                     for e in entries]
        self.k1, self.b = k1, b
        self.avgdl = sum(map(len, self.docs)) / len(self.docs)
        self.tf = [Counter(d) for d in self.docs]
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> list[float]:
        q = Counter(tokenize(query))
        out = []
        for tf, d in zip(self.tf, self.docs):
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avgdl))
            out.append(s)
        return out

    def top(self, query: str, k: int = 3) -> list[tuple[dict, float]]:
        ranked = sorted(zip(self.entries, self.scores(query)), key=lambda x: (-x[1], x[0]["id"]))
        return [(e, round(s, 4)) for e, s in ranked[:k] if s > 0]


def passage(entry: dict, words: int = PASSAGE_WORDS) -> str:
    text = f"{entry['description']}\nRemediation: {entry['remediation']}"
    toks = text.split()
    body = " ".join(toks[:words]) + (" ..." if len(toks) > words else "")
    return f"{entry['id']} {entry['title']}: {body}"


def taxonomy_entries(entries: list[dict] | None = None) -> list[dict]:
    """Only SWC entries that map to a dataset class (the model can output nothing else).

    Decided after measuring the unrestricted KB once (see README, M4); not tuned further.
    """
    from auditor.dataset import load_taxonomy

    mapped = {s for c in load_taxonomy()["classes"].values() for s in c["swc"]}
    return [e for e in (entries if entries is not None else load_kb()) if e["id"] in mapped]


_RETRIEVER: BM25 | None = None


def retrieve(code: str, k: int = 3) -> list[tuple[dict, float]]:
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = BM25(taxonomy_entries())
    return _RETRIEVER.top(code, k)
