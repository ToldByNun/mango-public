from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def parse_reasoning_payload(text: str) -> dict[str, Any]:
    """Extract a JSON object from a reasoning-model response."""
    if not text or not text.strip():
        return {}

    stripped = text.strip()
    for candidate in _candidate_json_blobs(stripped):
        parsed = _loads_object(candidate)
        if parsed is not None:
            return parsed
    return {}


def _candidate_json_blobs(text: str) -> list[str]:
    blobs: list[str] = [text]
    fenced = _FENCE.search(text)
    if fenced:
        blobs.append(fenced.group(1))
    start = text.find("{")
    if start >= 0:
        extracted = _extract_json_object(text, start)
        if extracted:
            blobs.append(extracted)
    return blobs


def _extract_json_object(text: str, start: int) -> str | None:
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _loads_object(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
