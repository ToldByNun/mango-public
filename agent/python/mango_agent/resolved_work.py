"""Language-agnostic tracking of work that is already done (anti-loop).

Gaps / claims are opaque strings from whatever checker produced them. This module
only diffs and matches text — it does not know about ``__main__``, ``int main``,
or any other language construct.
"""

from __future__ import annotations

import re

_STOP = frozenset(
    {
        "missing",
        "entry",
        "point",
        "looks",
        "incomplete",
        "stub",
        "body",
        "finish",
        "logic",
        "goal",
        "needs",
        "behavior",
        "matching",
        "function",
        "command",
        "code",
        "file",
        "empty",
        "syntax",
        "error",
        "line",
        "the",
        "and",
        "for",
        "each",
        "with",
        "from",
        "that",
        "this",
        "into",
        "only",
        "still",
        "listed",
        "above",
        "below",
        "present",
        "already",
    }
)

_WORD = re.compile(r"[A-Za-z_][\w']{2,}")


def normalize_claim(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def claim_body(item: str) -> str:
    """Strip optional ``path: `` prefix from a gap/claim string."""
    text = (item or "").strip()
    if ": " in text:
        path, rest = text.split(": ", 1)
        # Heuristic: path-like left side → keep the claim body only.
        if "/" in path or "\\" in path or path.endswith((".py", ".c", ".cpp", ".go", ".rs", ".js", ".ts", ".h")):
            return rest.strip()
    return text


def distinctive_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for word in _WORD.findall(text or ""):
        low = word.lower()
        if low in _STOP or low in seen:
            continue
        seen.add(low)
        tokens.append(low)
    return tokens


def closed_items(previously_open: list[str], currently_open: list[str]) -> list[str]:
    """Return items that were open before and are no longer open."""
    still = {normalize_claim(item) for item in currently_open}
    out: list[str] = []
    seen: set[str] = set()
    for item in previously_open:
        key = normalize_claim(item)
        if not key or key in still or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def merge_resolved(existing: list[str], newly: list[str], *, limit: int = 32) -> list[str]:
    """Append newly resolved claims, newest last, capped."""
    out = list(existing)
    have = {normalize_claim(item) for item in out}
    for item in newly:
        key = normalize_claim(item)
        if not key or key in have:
            continue
        have.add(key)
        out.append(item)
    if len(out) > limit:
        out = out[-limit:]
    return out


def thought_reasserts_resolved(thought: str, resolved: list[str]) -> list[str]:
    """Return resolved claims that the thought appears to treat as still open."""
    blob = normalize_claim(thought)
    if not blob or not resolved:
        return []
    hits: list[str] = []
    for item in resolved:
        body = claim_body(item)
        body_norm = normalize_claim(body)
        if body_norm and body_norm in blob:
            hits.append(item)
            continue
        tokens = distinctive_tokens(body)
        if not tokens:
            continue
        matched = sum(1 for tok in tokens if tok in blob)
        need = 1 if len(tokens) == 1 else max(2, (len(tokens) + 1) // 2)
        if matched >= need:
            hits.append(item)
    return hits
