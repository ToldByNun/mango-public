from __future__ import annotations

import traceback
from typing import Any

from mango_tools.tool_registry import ToolRegistry
from mango_tools.types import ToolCall, ToolResult


def run_tool_call(
    call: ToolCall,
    registry: ToolRegistry,
    *,
    context: dict[str, Any] | None = None,
) -> ToolResult:
    context = context or {}
    try:
        tool = registry.get(call.name)
        validated = tool.validate_arguments(dict(call.arguments))
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
