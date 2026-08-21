"""Verify all builtin tools against a user-style workspace (UI path simulation)."""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def main() -> int:
    from mango_agent.serve import resolve_run_workspace
    from mango_tools import create_default_registry, run_tool_call
    from mango_tools.types import ToolCall

    workspace = Path(tempfile.mkdtemp(prefix="mango-ui-verify-"))
    try:
        user_pick = workspace / "picked"
        user_pick.mkdir()
        resolved = resolve_run_workspace(str(user_pick), "verify-session")
        if resolved != user_pick.resolve():
            print(f"FAIL workspace resolution expected {user_pick} got {resolved}")
            return 1
        ctx = {"workspace": str(resolved)}
        reg = create_default_registry()
        call = lambda name, args: ToolCall(name=name, arguments=args, raw="", start=0, end=0)

        steps: list[tuple[str, str, dict]] = [
            (
                "write_file",
                "math_utils.py",
                {
                    "path": "home/user/math_utils.py",
                    "content": "def clamp(v, lo, hi):\n    return max(lo, min(hi, v))\n",
                },
            ),
            ("read_file", "read impl", {"path": "math_utils.py"}),
            (
                "write_file",
                "test file",
                {
                    "path": "user/test_math_utils.py",
                    "content": "from math_utils import clamp\n\ndef test_clamp():\n    assert clamp(5, 0, 10) == 5\n",
                },
            ),
            (
                "edit_file",
                "edit impl",
                {
                    "path": "math_utils.py",
                    "old_string": "return max(lo, min(hi, v))",
                    "new_string": "return min(hi, max(lo, v))",
                },
            ),
            ("run_tests", "pytest", {}),
            (
                "run_terminal_command",
                "shell",
                {"command": f'"{sys.executable}" -c "print(123)"', "timeout": 10},
            ),
            ("search_code", "search", {"pattern": "clamp", "path": "."}),
        ]

        for name, label, args in steps:
            t0 = time.monotonic()
            result = run_tool_call(call(name, args), reg, context=ctx)
            elapsed = time.monotonic() - t0
            if not result.success:
                print(f"FAIL {label}: {result.error}")
                return 2
            output = result.output if isinstance(result.output, dict) else {}
            if name in {"write_file", "edit_file", "read_file"}:
                path = output.get("path")
                abs_path = output.get("absolute_path")
                if not path or str(path).startswith("user/") or str(path).startswith("home/"):
                    print(f"FAIL {label}: bad display path {path!r}")
                    return 3
                if abs_path and not Path(str(abs_path)).is_file() and name != "read_file":
                    print(f"FAIL {label}: missing file {abs_path}")
                    return 4
            if name == "run_tests":
                if not output.get("ok"):
                    print(f"FAIL {label}: {output.get('stderr') or output.get('stdout')}")
                    return 5
                if output.get("timed_out"):
                    print(f"FAIL {label}: timed out")
                    return 6
            print(f"OK {label} ({elapsed:.2f}s)")

        impl = resolved / "math_utils.py"
        test = resolved / "test_math_utils.py"
        if not impl.is_file() or not test.is_file():
            print(f"FAIL files not at workspace root: {list(resolved.iterdir())}")
            return 7
        print(f"PASS workspace={resolved}")
        return 0
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
