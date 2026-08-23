from __future__ import annotations

import json
from pathlib import Path

from mango_tools import create_default_registry, parse_tool_calls, run_tool_call


def test_insert_lines_at_middle(tmp_path: Path) -> None:
    target = tmp_path / "bot.py"
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")

    payload = json.dumps({"path": str(target), "line": 2, "content": "inserted\n"})
    registry = create_default_registry()
    result = run_tool_call(parse_tool_calls(f"<tool_call=insert_lines : {payload}>")[0], registry)

    assert result.success
    assert target.read_text(encoding="utf-8") == "line1\ninserted\nline2\nline3\n"
    assert result.output["line"] == 2
    assert result.output["lines_inserted"] == 1


def test_insert_lines_appends_at_end(tmp_path: Path) -> None:
    target = tmp_path / "bot.py"
    target.write_text("async def on_message():\n    pass\n", encoding="utf-8")

    payload = json.dumps(
        {
            "path": str(target),
            "line": 3,
            "content": "\nif __name__ == '__main__':\n    bot.run(token)\n",
        }
    )
    registry = create_default_registry()
    result = run_tool_call(parse_tool_calls(f"<tool_call=insert_lines : {payload}>")[0], registry)

    assert result.success
    text = target.read_text(encoding="utf-8")
    assert "bot.run(token)" in text
    assert text.index("pass") < text.index("bot.run")


def test_insert_lines_requires_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "missing.py"
    payload = json.dumps({"path": str(target), "line": 1, "content": "x = 1\n"})
    registry = create_default_registry()
    result = run_tool_call(parse_tool_calls(f"<tool_call=insert_lines : {payload}>")[0], registry)
    assert not result.success
