"""Lightweight Luau source checks (no full parser — MVP verification helper)."""

from __future__ import annotations


def balance_ok(source: str) -> tuple[bool, str]:
    """Return (ok, detail) for basic bracket/string balance."""
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    i = 0
    n = len(source)
    in_str: str | None = None
    while i < n:
        ch = source[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in "\"'":
            in_str = ch
            i += 1
            continue
        if ch == "-" and i + 1 < n and source[i + 1] == "-":
            # comment to EOL
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack[-1] != pairs[ch]:
                return False, f"unbalanced '{ch}' at index {i}"
            stack.pop()
        i += 1
    if in_str:
        return False, "unterminated string"
    if stack:
        return False, f"unclosed {stack[-1]!r}"
    return True, "ok"
