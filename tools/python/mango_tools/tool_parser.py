from __future__ import annotations

import json
import re
from typing import Any

from mango_tools.types import ToolCall

_OPEN_TAG = re.compile(
    r"<\s*tool_call\s*=\s*([A-Za-z_][A-Za-z0-9_-]*)\s*:?\s*",
    re.IGNORECASE,
)
_XML_TAG = re.compile(
    r'<\s*tool_call\s+name\s*=\s*["\']([A-Za-z_][A-Za-z0-9_-]*)["\']\s*>\s*',
    re.IGNORECASE,
)

# Models often invent `<write_file | {...}>` instead of `<tool_call=write_file : {...}>`.
_TOOL_NAMES = (
    "write_file|edit_file|read_file|edit_symbol|rename_symbol|search_code|"
    "codebase_lookup|ask_epistemic|declare_apis|run_terminal_command|measure|run_tests"
)
_INFORMAL_TAG = re.compile(
    rf"<\s*({_TOOL_NAMES})\s*[|:]\s*",
    re.IGNORECASE,
)


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Extract embedded tool calls from model output."""
    calls: list[ToolCall] = []
    seen: set[tuple[int, str]] = set()
    for pattern in (_OPEN_TAG, _XML_TAG, _INFORMAL_TAG):
        for match in pattern.finditer(text):
            name = match.group(1)
            json_start = match.end()
            json_text, json_end = _extract_json_object(text, json_start)
            if json_text is None:
                continue
            arguments = _parse_arguments_json(json_text)
            if arguments is None:
                continue
            if name.replace("-", "_").lower() == "write_file":
                fenced, fence_end, fence_complete = _extract_fenced_content(text, json_end)
                if fenced is not None and fence_complete:
                    arguments["content"] = fenced
                    json_end = fence_end
                elif fenced is not None and not fence_complete:
                    # Truncated generation: do not treat partial fence as a successful write.
                    continue
            if name.replace("-", "_").lower() == "write_file" and not str(arguments.get("content") or ""):
                continue
            key = (match.start(), name)
            if key in seen:
                continue
            seen.add(key)
            end = _find_closing_bracket(text, json_end)
            close = text.find("</tool_call>", json_end)
            if close != -1 and (end <= json_end or close + 12 > end):
                end = close + len("</tool_call>")
            raw = text[match.start() : end]
            calls.append(
                ToolCall(
                    name=name,
                    arguments=arguments,
                    raw=raw,
                    start=match.start(),
                    end=end,
                )
            )
    calls.sort(key=lambda item: item.start)
    return calls


def _extract_json_object(text: str, start: int) -> tuple[str | None, int]:
    i = start
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text) or text[i] != "{":
        return None, start

    depth = 0
    in_string = False
    escape = False
    quote_char = ""

    for j in range(i, len(text)):
        ch = text[j]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote_char:
                in_string = False
            continue

        if ch in ('"', "'"):
            in_string = True
            quote_char = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1], j + 1
    return None, start


def _extract_fenced_content(text: str, after_json: int) -> tuple[str | None, int, bool]:
    """Return (content, end_index, fence_closed).

    If the opening ``` is present but the closing fence is missing, content is
    the partial body and fence_closed is False — callers must not write it.
    """
    rest = text[after_json:]
    start = rest.find("```")
    if start < 0:
        return None, after_json, True
    body = start + 3
    if body < len(rest) and rest[body] in "\r\n":
        body += 1
        if rest[body - 1] == "\r" and body < len(rest) and rest[body] == "\n":
            body += 1
    else:
        nl = rest.find("\n", body)
        lang = rest[body:nl].strip() if nl != -1 else rest[body:].strip()
        if nl != -1 and lang.replace("+", "").isalnum():
            body = nl + 1
    end = rest.find("```", body)
    if end < 0:
        content = rest[body:]
        return content, after_json + len(rest), False
    content = rest[body:end]
    if content.startswith("python\n"):
        content = content[7:]
    return content, after_json + end + 3, True


def _find_closing_bracket(text: str, after_json: int) -> int:
    i = after_json
    while i < len(text) and text[i].isspace():
        i += 1
    if i < len(text) and text[i : i + 2] == "/>":
        return i + 2
    if i < len(text) and text[i] == ">":
        return i + 1
    return after_json


def _parse_arguments_json(raw_json: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        try:
            parsed = _parse_lenient_json(raw_json)
        except json.JSONDecodeError:
            return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _parse_lenient_json(raw_json: str) -> Any:
    normalized = raw_json.strip()
    if not normalized:
        raise json.JSONDecodeError("empty", raw_json, 0)

    attempt = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', normalized)
    attempt = re.sub(r",\s*([}\]])", r"\1", attempt)
    return json.loads(attempt)
