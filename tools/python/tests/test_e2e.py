from __future__ import annotations

import json
from pathlib import Path

from mango_tools import create_default_registry, parse_tool_calls, run_tool_call


def test_e2e_read_file_from_model_output(tmp_path: Path) -> None:
    sample = tmp_path / "hello.txt"
    sample.write_text("Mango tools OK\n", encoding="utf-8")

    model_output = (
        "I'll read the file for you.\n"
        f'<tool_call=read_file : {json.dumps({"path": str(sample)})}>\n'
        "Done."
    )

    registry = create_default_registry()
    calls = parse_tool_calls(model_output)
    assert len(calls) == 1
    assert calls[0].name == "read_file"

    result = run_tool_call(calls[0], registry)
    assert result.success is True
    assert result.tool_name == "read_file"
    assert result.error is None
    assert result.output["content"] == "Mango tools OK\n"
    assert result.output["path"] == str(sample.resolve())
    assert result.to_dict()["success"] is True


def test_e2e_write_and_edit_file(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"

    write_output = (
        f'<tool_call=write_file : {json.dumps({"path": str(target), "content": "alpha"})}>'
    )
    edit_output = (
        f'<tool_call=edit_file : {json.dumps({"path": str(target), "old_string": "alpha", "new_string": "beta"})}>'
    )

    registry = create_default_registry()

    write_result = run_tool_call(parse_tool_calls(write_output)[0], registry)
    assert write_result.success
    assert target.read_text(encoding="utf-8") == "alpha"

    edit_result = run_tool_call(parse_tool_calls(edit_output)[0], registry)
    assert edit_result.success
    assert edit_result.output["replacements"] == 1
    assert target.read_text(encoding="utf-8") == "beta"


def test_e2e_edit_file_fuzzy_indent(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("def f():\n\treturn 1\n", encoding="utf-8")
    edit_output = (
        f'<tool_call=edit_file : {json.dumps({"path": str(target), "old_string": "    return 1", "new_string": "    return 2"})}>'
    )
    registry = create_default_registry()
    result = run_tool_call(parse_tool_calls(edit_output)[0], registry)
    assert result.success
    assert result.output.get("fuzzy") is True
    assert result.output.get("match") == "indent"
    assert target.read_text(encoding="utf-8") == "def f():\n\treturn 2\n"


def test_e2e_edit_symbol_from_model_output(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("def greet(name):\n    return name\n\ndef other():\n    return 1\n", encoding="utf-8")
    payload = json.dumps(
        {"path": str(target), "symbol": "greet", "body": "return f'hi {name}'"}
    )
    model_output = f"<tool_call=edit_symbol : {payload}>"
    registry = create_default_registry()
    result = run_tool_call(parse_tool_calls(model_output)[0], registry)
    assert result.success
    assert result.output["symbol"] == "greet"
    text = target.read_text(encoding="utf-8")
    assert "hi {name}" in text
    assert "def other():" in text


def test_e2e_search_code(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def hello(): pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("print('hello')\n", encoding="utf-8")

    model_output = (
        f'<tool_call=search_code : {json.dumps({"pattern": "hello", "path": str(tmp_path)})}>'
    )
    registry = create_default_registry()
    result = run_tool_call(parse_tool_calls(model_output)[0], registry)

    assert result.success
    assert result.output["match_count"] == 2


def test_e2e_unknown_tool_returns_error() -> None:
    model_output = '<tool_call=nonexistent : {"x": 1}>'
    registry = create_default_registry()
    result = run_tool_call(parse_tool_calls(model_output)[0], registry)
    assert result.success is False
    assert "Unknown tool" in (result.error or "")
