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


def test_argument_aliases_applied_on_execution(tmp_path) -> None:
    from mango_tools.tool_executor import run_tool_call
    from mango_tools.types import ToolCall

    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")

    registry = create_default_registry(enable_delete=True)
    call = ToolCall(
        name="read_file",
        arguments={"file_path": str(target)},  # Anthropic-style name, not "path"
        raw="",
        start=0,
        end=0,
    )
    result = run_tool_call(call, registry, context={})
    assert result.success, result.error
    assert result.output["content"] == "hello"


def test_builtin_tools_registered() -> None:
    registry = create_default_registry(enable_delete=True)
    names = registry.list_tools()
    assert names == [
        "delete_file",
        "edit_file",
        "edit_symbol",
        "glob_files",
        "list_dir",
        "measure",
        "read_file",
        "rename_symbol",
        "run_terminal_command",
        "run_tests",
        "search_code",
        "write_file",
    ]


def test_delete_tool_gated_by_checkpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANGO_FILE_CHECKPOINTS", "0")
    monkeypatch.delenv("MANGO_DELETE_TOOL", raising=False)
    names = create_default_registry().list_tools()
    assert "delete_file" not in names


def test_missing_required_args_raises() -> None:
    registry = create_default_registry()
    tool = registry.get("read_file")
    with pytest.raises(ValueError, match="Missing required arguments"):
        tool.validate_arguments({})
