"""Mango Tools — tool calling parser, registry, and built-in implementations."""

from mango_tools.format import format_tool_call, tool_call_instruction
from mango_tools.gbnf import tool_call_gbnf
from mango_tools.implementations import create_default_registry, register_builtin_tools
from mango_tools.tool_executor import run_tool_call, run_tool_calls
from mango_tools.tool_parser import parse_tool_calls
from mango_tools.tool_registry import ToolRegistry
from mango_tools.types import ToolCall, ToolDefinition, ToolResult, ToolSchema

__all__ = [
    "ToolCall",
    "ToolDefinition",
    "ToolRegistry",
    "ToolResult",
    "ToolSchema",
    "create_default_registry",
    "format_tool_call",
    "parse_tool_calls",
    "register_builtin_tools",
    "run_tool_call",
    "run_tool_calls",
    "tool_call_gbnf",
    "tool_call_instruction",
]
