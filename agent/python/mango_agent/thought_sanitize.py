from __future__ import annotations

import re

# Qwen/Gemma and similar models emit … wrappers.
_THINK_TAG = r"(?:redacted_thinking|think(?:ing)?)"
_THINK_BLOCK_RE = re.compile(
    rf"<\s*{_THINK_TAG}\b[^>]*>([\s\S]*?)<\s*/\s*{_THINK_TAG}\s*>",
    re.IGNORECASE,
)
_THINK_OPEN_OR_CLOSE_RE = re.compile(rf"<\s*/?\s*{_THINK_TAG}\b[^>]*>", re.IGNORECASE)
_THINK_PARTIAL_END_RE = re.compile(rf"<\s*/?\s*{_THINK_TAG}\b[^>]*$", re.IGNORECASE)
_CHANNEL_RE = re.compile(r"<\|?channel\|?>", re.IGNORECASE)
_FENCE_RE = re.compile(r"```[\w+-]*\n[\s\S]*?```", re.MULTILINE)


def strip_thought_markup(text: str) -> str:
    if not text:
        return ""
    cuts = []
    for pat in (r"<tool_call\b", r"<\s*write_file\b"):
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            cuts.append(m.start())
    cut_at = min(cuts) if cuts else None
    head = text[:cut_at] if cut_at is not None else text
    dump = re.search(r"[A-Za-z_][\w.]*\([^)]*\)\s*\|", head)
    until_dump = head[: dump.start()] if dump else head
    cleaned = _CHANNEL_RE.sub("", until_dump)
    cleaned = _THINK_BLOCK_RE.sub(r"\1", cleaned)
    cleaned = _THINK_OPEN_OR_CLOSE_RE.sub("", cleaned)
    cleaned = _THINK_PARTIAL_END_RE.sub("", cleaned)
    cleaned = re.sub(r"<[^>]*$", "", cleaned)
    cleaned = _FENCE_RE.sub("", cleaned)
    cleaned = re.sub(r"<tool(?:_call\b[\s\S]*)?$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def is_empty_thought(text: str) -> bool:
    return not strip_thought_markup(text).strip()
