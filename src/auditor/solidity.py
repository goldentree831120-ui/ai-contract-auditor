"""Small, dependency-free helpers for working with Solidity source text.

These are text-level tools (not a full parser). They are good enough for the
short, single-file contracts in this dataset and are unit-tested in tests/.
"""

from __future__ import annotations

import re

_IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

# A line that opens a callable unit. Old-style constructors are plain
# "function Name(", so they are covered by the function pattern.
_HEADER_RE = re.compile(
    r"^\s*(?:function\s*(?P<fname>[A-Za-z_$][A-Za-z0-9_$]*)?\s*\(|"
    r"(?P<ctor>constructor)\s*\(|"
    r"modifier\s+(?P<mname>[A-Za-z_$][A-Za-z0-9_$]*)|"
    r"(?P<fallback>fallback|receive)\s*\()"
)


def strip_comments(src: str) -> str:
    """Remove // and /* */ comments, leaving string literals untouched.

    Newlines inside block comments are kept so that line structure survives;
    normalize() removes the resulting comment-only lines afterwards.
    """
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c in ('"', "'"):
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(src[i : j + 1])
            i = j + 1
        elif c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                i += 1
        elif c == "/" and nxt == "*":
            end = src.find("*/", i + 2)
            end = n if end == -1 else end + 2
            out.append("\n" * src.count("\n", i, end))
            i = end
        else:
            out.append(c)
            i += 1
    return "".join(out)


def has_comments(src: str) -> bool:
    """True if the source contains any comment outside string literals."""
    return strip_comments(src) != src


def normalize(src: str) -> str:
    """Trim trailing spaces, drop blank runs to one blank line, trim ends."""
    lines = [ln.rstrip() for ln in src.replace("\r\n", "\n").split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln == "" and (not out or out[-1] == ""):
            continue
        out.append(ln)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def sanitize(src: str, renames: dict[str, str] | None = None, prepend: str = "") -> str:
    """Comment-free, normalized source with optional whole-word renames."""
    stripped = strip_comments(src)  # keeps newlines, so lines stay aligned
    kept = [
        new
        for old_line, new in zip(src.split("\n"), stripped.split("\n"))
        if new.strip() or not old_line.strip()  # drop lines that held only a comment
    ]
    text = "\n".join(kept)
    for old in sorted(renames or {}, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(old)}\b", renames[old], text)
    if prepend:
        text = prepend.rstrip() + "\n\n" + text
    return normalize(text)


def squash(s: str) -> str:
    """Remove all whitespace (used for whitespace-insensitive matching)."""
    return re.sub(r"\s+", "", s)


def find_anchor(src: str, anchor: str) -> list[int]:
    """1-based line numbers whose text contains `anchor`, ignoring whitespace."""
    key = squash(anchor)
    return [i for i, ln in enumerate(src.split("\n"), start=1) if key and key in squash(ln)]


def identifiers(src: str) -> set[str]:
    """All identifier-like tokens outside string literals and comments."""
    code = strip_comments(src)
    code = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', code)
    return set(_IDENT_RE.findall(code))


def enclosing_function(src: str, line: int) -> str:
    """Name of the function/constructor/modifier containing a 1-based line.

    Returns "constructor", "fallback", "receive", a function or modifier name,
    or "<contract-level>" for lines outside any callable body. A nameless
    old-style "function ()" is reported as "fallback".
    """
    lines = src.split("\n")
    depth = 0
    current: str | None = None
    current_depth = -1
    pending: str | None = None
    for idx, raw in enumerate(lines, start=1):
        text = strip_comments(raw)
        m = _HEADER_RE.match(text)
        if m and current is None:
            if m.group("ctor"):
                pending = "constructor"
            elif m.group("mname"):
                pending = m.group("mname")
            elif m.group("fallback"):
                pending = m.group("fallback")
            else:
                pending = m.group("fname") or "fallback"
        if pending is not None and current is None and idx == line and "{" not in text:
            return pending
        for ch in text:
            if ch == "{":
                depth += 1
                if pending is not None and current is None:
                    current, current_depth, pending = pending, depth, None
            elif ch == "}":
                if current is not None and depth == current_depth:
                    if idx == line:
                        return current
                    current, current_depth = None, -1
                depth -= 1
            elif ch == ";" and pending is not None and current is None:
                pending = None
        if idx == line:
            return current or pending or "<contract-level>"
    return "<contract-level>"


def pragma_version(src: str) -> str | None:
    m = re.search(r"pragma\s+solidity\s+([^;]+);", src)
    return m.group(1).strip() if m else None
