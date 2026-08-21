from __future__ import annotations

from pathlib import Path

import pytest

from mango_tools.implementations.rename_symbol import rename_symbol
from mango_tools.implementations.write_file import write_file


def test_rename_symbol_updates_definition_and_imports(tmp_path: Path) -> None:
    greeter = tmp_path / "greeter.py"
    greeter.write_text("def greet(name):\n    return f'hi {name}'\n", encoding="utf-8")
    app = tmp_path / "app.py"
    app.write_text("from greeter import greet\n\n\ndef run():\n    return greet('Ada')\n", encoding="utf-8")
    result = rename_symbol("greet", "welcome", path=str(tmp_path))
    assert result["old_name"] == "greet"
    assert len(result["files"]) == 2
    assert "def welcome(name):" in greeter.read_text(encoding="utf-8")
    app_text = app.read_text(encoding="utf-8")
    assert "from greeter import welcome" in app_text
    assert "return welcome('Ada')" in app_text
    assert "import greet" not in app_text
    assert " greet(" not in app_text and not app_text.startswith("greet(")


def test_rename_symbol_does_not_skip_workspace_inside_dot_mango(tmp_path: Path) -> None:
    workspace = tmp_path / ".mango" / "task"
    workspace.mkdir(parents=True)
    greeter = workspace / "greeter.py"
    greeter.write_text("def greet(name):\n    return name\n", encoding="utf-8")
    app = workspace / "app.py"
    app.write_text("from greeter import greet\n\n\ndef run():\n    return greet('Ada')\n", encoding="utf-8")
    result = rename_symbol("greet", "welcome", path=str(workspace))
    assert len(result["files"]) == 2
    assert "from greeter import welcome" in app.read_text(encoding="utf-8")


def test_rename_symbol_does_not_rename_import_module(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("import greet\n\n\ndef run():\n    return greet.x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="file unchanged"):
        rename_symbol("greet", "welcome", path=str(target))
    assert "import greet" in target.read_text(encoding="utf-8")


def test_write_file_rejects_identical_content(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="file unchanged"):
        write_file(str(target), "x = 1\n")
