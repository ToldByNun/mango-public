from __future__ import annotations

from mango_tools.implementations.edit_file import edit_file
from mango_tools.implementations.edit_symbol import edit_symbol
from mango_tools.implementations.measure import measure
from mango_tools.implementations.read_file import read_file
from mango_tools.implementations.rename_symbol import rename_symbol
from mango_tools.implementations.run_tests import run_tests
from mango_tools.implementations.run_terminal_command import run_terminal_command
from mango_tools.implementations.search_code import search_code
from mango_tools.implementations.write_file import write_file
from mango_tools.tool_registry import ToolRegistry


def register_builtin_tools(registry: ToolRegistry) -> None:
    registry.register(
        "read_file",
        read_file,
        description="Read the contents of a file.",
        parameters={
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"},
            "max_bytes": {"type": "integer", "description": "Optional read cap in bytes"},
        },
        required=["path"],
    )
    registry.register(
        "write_file",
        write_file,
        description="Write text content to a file.",
        parameters={
            "path": {"type": "string", "description": "Target file path"},
            "content": {"type": "string", "description": "Full file content"},
            "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"},
            "create_dirs": {"type": "boolean", "description": "Create parent dirs", "default": True},
        },
        required=["path", "content"],
    )
    registry.register(
        "edit_file",
        edit_file,
        description="Replace a unique string snippet inside a file.",
        parameters={
            "path": {"type": "string", "description": "Target file path"},
            "old_string": {"type": "string", "description": "Text to replace"},
            "new_string": {"type": "string", "description": "Replacement text"},
            "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"},
            "replace_all": {"type": "boolean", "description": "Replace all occurrences", "default": False},
        },
        required=["path", "old_string", "new_string"],
    )
    registry.register(
        "edit_symbol",
        edit_symbol,
        description="Replace a function/class/method by name, or append it if missing. Preferred over edit_file for Python.",
        parameters={
            "path": {"type": "string", "description": "Target Python file path"},
            "symbol": {"type": "string", "description": "Function, class, or Class.method name"},
            "body": {
                "type": "string",
                "description": "New body statements, or a full def/class block",
            },
            "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"},
        },
        required=["path", "symbol", "body"],
    )
    registry.register(
        "rename_symbol",
        rename_symbol,
        description="Rename a Python identifier in a file or workspace (definition and references).",
        parameters={
            "old_name": {"type": "string", "description": "Current identifier"},
            "new_name": {"type": "string", "description": "New identifier"},
            "path": {
                "type": "string",
                "description": "File or directory to rename in",
                "default": ".",
            },
            "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"},
        },
        required=["old_name", "new_name"],
    )
    registry.register(
        "search_code",
        search_code,
        description="Search for a regex pattern in files under a directory.",
        parameters={
            "pattern": {"type": "string", "description": "Regex pattern"},
            "path": {"type": "string", "description": "Root file or directory", "default": "."},
            "case_insensitive": {"type": "boolean", "description": "Case-insensitive search", "default": False},
            "max_results": {"type": "integer", "description": "Maximum matches to return", "default": 50},
        },
        required=["pattern"],
    )
    registry.register(
        "measure",
        measure,
        description="Repeat a short command and return median wall time in milliseconds.",
        parameters={
            "command": {
                "type": "string",
                "description": "Shell command to time (python -m timeit ... or a bench script)",
            },
            "repeats": {
                "type": "integer",
                "description": "Number of samples (default 5, max 15)",
                "default": 5,
            },
        },
        required=["command"],
    )
    registry.register(
        "run_tests",
        run_tests,
        description="Run the workspace test suite (pytest) and return the compact report.",
        parameters={},
        required=[],
    )
    registry.register(
        "run_terminal_command",
        run_terminal_command,
        description="Execute a shell command and return captured output.",
        parameters={
            "command": {"type": "string", "description": "Shell command to run"},
            "cwd": {"type": "string", "description": "Optional working directory"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
        },
        required=["command"],
    )


def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    return registry
