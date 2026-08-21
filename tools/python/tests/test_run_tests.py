from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from mango_tools.implementations.run_terminal_command import run_terminal_command
from mango_tools.implementations.run_tests import run_tests


def test_run_tests_requires_workspace() -> None:
    try:
        run_tests()
    except ValueError as exc:
        assert "workspace" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")


def test_run_tests_runs_pytest(tmp_path: Path) -> None:
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    result = run_tests(_context={"workspace": str(tmp_path)})
    assert result["mode"] == "pytest"
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["cwd"] == str(tmp_path.resolve())


def test_run_tests_uses_devnull_stdin(tmp_path: Path) -> None:
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    with patch("mango_tools.implementations.run_tests.subprocess.run") as mocked:
        mocked.return_value = type("R", (), {"returncode": 0})()
        run_tests(_context={"workspace": str(tmp_path)})
        assert mocked.call_args.kwargs.get("stdin") == subprocess.DEVNULL


def test_run_tests_handles_verbose_output(tmp_path: Path) -> None:
    helper = tmp_path / "noisy_helper.py"
    helper.write_text(
        "def spam():\n"
        + "".join(f"    print('line', {i})\n" for i in range(200))
        + "    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "test_ok.py").write_text(
        "from noisy_helper import spam\n\n"
        "def test_ok():\n"
        "    assert spam()\n",
        encoding="utf-8",
    )
    result = run_tests(_context={"workspace": str(tmp_path)})
    assert result["ok"] is True
    assert not result["timed_out"]


def test_run_terminal_command_defaults_cwd_to_workspace(tmp_path: Path) -> None:
    marker = tmp_path / "here.txt"
    marker.write_text("ok\n", encoding="utf-8")
    result = run_terminal_command(
        f'{sys.executable} -c "print(open(\'here.txt\').read())"',
        _context={"workspace": str(tmp_path)},
    )
    assert result["exit_code"] == 0
    assert result["cwd"] == str(tmp_path.resolve())
    assert "ok" in (result["stdout"] or "")
