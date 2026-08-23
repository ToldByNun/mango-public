from __future__ import annotations

import json
from typing import Any

# Canonical embed format the model is instructed to emit:
#   <tool_call=tool_name : {"arg1": "value"}>
TOOL_CALL_PREFIX = "<tool_call="
TOOL_CALL_SUFFIX = ">"


def format_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Serialize a tool call into the canonical embed format."""
    payload = json.dumps(arguments, ensure_ascii=False, separators=(",", ": "))
    return f"{TOOL_CALL_PREFIX}{name} : {payload}{TOOL_CALL_SUFFIX}"


def tool_call_instruction() -> str:
    """Short spec string for system prompts (used by agent/context later)."""
    return (
        "Emit exactly one tool call:\n"
        f"  {TOOL_CALL_PREFIX}<tool_name> : {{\"arg\": \"value\"}}{TOOL_CALL_SUFFIX}\n"
        "For new files: write_file the COMPLETE file in one call. "
        "To extend an existing file: insert_lines with a fenced multi-line block "
        "(not tiny edit_file patches). "
        "Stop after the tool call."
    )
