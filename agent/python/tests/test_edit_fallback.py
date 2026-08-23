"""Agent-side edit recovery: failed edit_file must land a write, not loop."""

from __future__ import annotations

from pathlib import Path

from mango_agent.agent import Agent
from mango_runtime.types import CompletionResult
from mango_tools.types import ToolCall, ToolResult


class _DummyModel:
    def complete(self, *args, **kwargs):
        return CompletionResult(text="", prompt_tokens=0, completion_tokens=0, total_tokens=0)


def test_fallback_recovers_main_guard(tmp_path: Path) -> None:
    target = tmp_path / "wordstats.py"
    target.write_text("def main():\n    print('hi')\n", encoding="utf-8")
    agent = Agent(
        model_runner=_DummyModel(),
        require_tools=True,
        verification_root=str(tmp_path),
        codeintel_root=str(tmp_path),
    )
    call = ToolCall(
        name="edit_file",
        arguments={
            "path": "wordstats.py",
            "old_string": "def main():\n    print('bye')\n",
            "new_string": (
                "def main():\n    print('hi')\n\n"
                "if __name__ == '__main__':\n    main()\n"
            ),
        },
        raw="",
        start=0,
        end=0,
    )
    failed = ToolResult(
        success=False,
        tool_name="edit_file",
        error="old_string not found in file",
        call=call,
    )
    out = agent._fallback_failed_edits([failed])
    assert len(out) == 1
    assert out[0].success is True
    assert out[0].tool_name == "write_file"
    text = target.read_text(encoding="utf-8")
    assert "if __name__" in text
    assert "print('hi')" in text
