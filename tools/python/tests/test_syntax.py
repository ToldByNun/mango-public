from __future__ import annotations

from pathlib import Path

import pytest

from mango_tools.implementations.write_file import write_file
from mango_tools.syntax import collect_python_syntax_errors, python_syntax_error, salvage_python_source


def test_python_syntax_error_reports_line(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def unique(items)\n    return list(items)\n", encoding="utf-8")
    err = python_syntax_error(path)
    assert err is not None
    assert "broken.py" in err
    assert python_syntax_error(tmp_path / "ok.py", source="def unique(items):\n    return items\n") is None


def test_write_file_attaches_syntax_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    result = write_file(str(path), "def unique(items)\n    return 1\n")
    assert "syntax_error" in result
    assert "broken.py" in result["syntax_error"]


def test_collect_skips_valid_files(tmp_path: Path) -> None:
    good = tmp_path / "good.py"
    bad = tmp_path / "bad.py"
    good.write_text("x = 1\n", encoding="utf-8")
    bad.write_text("def f(\n", encoding="utf-8")
    errors = collect_python_syntax_errors([good, bad])
    assert len(errors) == 1
    assert "bad.py" in errors[0]


def test_salvage_python_drops_truncated_tail() -> None:
    source = "x = 1\n\ndef foo():\n    return 1\n\nself._executor = ThreadPoolEx(\n"
    salvaged = salvage_python_source(source)
    assert salvaged is not None
    assert "foo" in salvaged
    assert "ThreadPoolEx" not in salvaged
    assert python_syntax_error("ok.py", source=salvaged) is None


def test_write_file_rejects_truncated_replacement(tmp_path: Path) -> None:
    path = tmp_path / "uniqueutil.py"
    original = "def unique(items)\n    return sorted(set(items))\n"
    path.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError, match="truncated"):
        write_file(str(path), "def")
    assert path.read_text(encoding="utf-8") == original


def test_write_file_relative_uses_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "proj"
    workspace.mkdir()
    result = write_file("note.txt", "hello\n", _context={"workspace": str(workspace)})
    target = workspace / "note.txt"
    assert target.read_text(encoding="utf-8") == "hello\n"
    assert result["path"] == "note.txt"
    assert Path(result["absolute_path"]) == target.resolve()
