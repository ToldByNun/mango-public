from __future__ import annotations

import pytest

from mango_tools.implementations import create_default_registry, register_builtin_tools
from mango_tools.tool_registry import ToolRegistry


def test_register_and_get_tool() -> None:
    registry = ToolRegistry()

    @registry.tool("echo", description="Echo input", parameters={"message": {}}, required=["message"])
    def echo(message: str) -> str:
        return message

    tool = registry.get("echo")
    assert tool.name == "echo"
    assert tool.handler("hi") == "hi"


def test_duplicate_registration_raises() -> None:
    registry = ToolRegistry()
    registry.register("x", lambda: None)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("x", lambda: None)


def test_builtin_tools_registered() -> None:
    registry = create_default_registry()
    names = registry.list_tools()
    assert names == [
        "edit_file",
        "edit_symbol",
        "measure",
        "read_file",
        "rename_symbol",
        "run_terminal_command",
        "run_tests",
        "search_code",
        "write_file",
    ]


def test_missing_required_args_raises() -> None:
    registry = create_default_registry()
    tool = registry.get("read_file")
    with pytest.raises(ValueError, match="Missing required arguments"):
        tool.validate_arguments({})
