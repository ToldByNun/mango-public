from __future__ import annotations

import traceback
from typing import Any

from mango_tools.tool_registry import ToolRegistry
from mango_tools.types import ToolCall, ToolResult

# Anthropic-style parameter names some quantized models fall back to, mapped to
# our canonical argument names. Checked before validation so a recovered XML
# call executes instead of failing with "Missing required arguments".
_ARGUMENT_ALIASES: dict[str, dict[str, str]] = {
    "read_file": {"file_path": "path", "filepath": "path"},
    "write_file": {"file_path": "path", "filepath": "path", "file_text": "content"},
    "edit_file": {"file_path": "path", "filepath": "path"},
    "edit_symbol": {"file_path": "path", "filepath": "path"},
    "delete_file": {"file_path": "path", "filepath": "path"},
    "rename_symbol": {"file_path": "path", "filepath": "path"},
    "run_terminal_command": {"cmd": "command"},
    "search_code": {"query": "pattern", "regex": "pattern"},
}


def _apply_argument_aliases(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    aliases = _ARGUMENT_ALIASES.get(name)
    if not aliases:
        return arguments
    resolved = dict(arguments)
    for source, target in aliases.items():
        if target in resolved or source not in resolved:
            continue
        resolved[target] = resolved.pop(source)
    return resolved


def run_tool_call(
    call: ToolCall,
    registry: ToolRegistry,
    *,
    context: dict[str, Any] | None = None,
) -> ToolResult:
    context = context or {}
    try:
        tool = registry.get(call.name)
        arguments = _apply_argument_aliases(call.name, dict(call.arguments))
        validated = tool.validate_arguments(arguments)
        output = tool.handler(**validated, _context=context)
        return ToolResult(
            success=True,
            tool_name=call.name,
            output=output,
            call=call,
        )
    except KeyError as exc:
        return ToolResult(
            success=False,
            tool_name=call.name,
            error=str(exc),
            call=call,
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(
            success=False,
            tool_name=call.name,
            error=str(exc),
            call=call,
            metadata={"traceback": traceback.format_exc()},
        )


def run_tool_calls(
    calls: list[ToolCall],
    registry: ToolRegistry,
    *,
    context: dict[str, Any] | None = None,
) -> list[ToolResult]:
    """Execute tool calls in the order they appeared in the model output."""
    context = context or {}
    cancelled = context.get("_cancelled")
    results: list[ToolResult] = []
    for call in calls:
        if callable(cancelled) and cancelled():
            results.append(
                ToolResult(
                    success=False,
                    tool_name=call.name,
                    error="cancelled",
                    call=call,
                    metadata={"cancelled": True},
                )
            )
            break
        results.append(run_tool_call(call, registry, context=context))
    return results
