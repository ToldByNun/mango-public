from __future__ import annotations

from pathlib import Path

import pytest

from mango_tools.implementations.edit_symbol import edit_symbol


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_edit_symbol_replaces_body_and_keeps_neighbors(tmp_path: Path) -> None:
    target = _write(
        tmp_path / "mod.py",
        "PAD = 1\n\n"
        "def greet(name):\n"
        "    return f'hi {name}'\n\n"
        "def other():\n"
        "    return 7\n",
    )
    result = edit_symbol(str(target), "greet", "return f'Hello, {name}!'")
    text = target.read_text(encoding="utf-8")
    assert result["symbol"] == "greet"
    assert result["kind"] == "function"
    assert "return f'Hello, {name}!'" in text
    assert "def greet(name):" in text
    assert "def other():" in text
    assert "return 7" in text
    assert "PAD = 1" in text
    assert "hi {name}" not in text


def test_edit_symbol_accepts_full_def_and_can_change_signature(tmp_path: Path) -> None:
    target = _write(
        tmp_path / "mod.py",
        "def greet(name):\n    return name\n",
    )
    edit_symbol(
        str(target),
        "greet",
        "def greet(name, excited=False):\n    mark = '!' if excited else ''\n    return f'Hello, {name}{mark}'\n",
    )
    text = target.read_text(encoding="utf-8")
    assert "def greet(name, excited=False):" in text
    assert "excited" in text


def test_edit_symbol_preserves_decorator_on_body_edit(tmp_path: Path) -> None:
    target = _write(
        tmp_path / "mod.py",
        "@staticmethod\n"
        "def greet(name):\n"
        "    return name\n",
    )
    edit_symbol(str(target), "greet", "return f'Hello, {name}!'")
    text = target.read_text(encoding="utf-8")
    assert "@staticmethod" in text
    assert "def greet(name):" in text
    assert "Hello" in text


def test_edit_symbol_method_via_qualname(tmp_path: Path) -> None:
    target = _write(
        tmp_path / "mod.py",
        "class Greeter:\n"
        "    def greet(self, name):\n"
        "        return name\n"
        "    def ping(self):\n"
        "        return 1\n",
    )
    edit_symbol(str(target), "Greeter.greet", "return f'Hello, {name}!'")
    text = target.read_text(encoding="utf-8")
    assert "class Greeter:" in text
    assert "return f'Hello, {name}!'" in text
    assert "def ping(self):" in text
    assert "return 1" in text


def test_edit_symbol_hoists_imports_instead_of_nesting_def(tmp_path: Path) -> None:
    target = _write(tmp_path / "jsonutil.py", "def to_json(obj):\n    return str(obj)\n")
    edit_symbol(
        str(target),
        "to_json",
        "import json\n\n\ndef to_json(obj):\n    return json.dumps(obj)\n",
    )
    text = target.read_text(encoding="utf-8")
    compile(text, str(target), "exec")
    ns: dict[str, object] = {}
    exec(text, ns)
    assert ns["to_json"]({"a": 1}) == '{"a": 1}'
    assert text.startswith("import json")
    assert text.count("def to_json") == 1


def test_edit_symbol_hoists_import_with_return_body(tmp_path: Path) -> None:
    target = _write(tmp_path / "jsonutil.py", "def to_json(obj):\n    return str(obj)\n")
    edit_symbol(str(target), "to_json", "import json\nreturn json.dumps(obj)")
    text = target.read_text(encoding="utf-8")
    assert text.startswith("import json")
    assert "    return json.dumps(obj)" in text
    assert "def to_json" in text
    original = "def greet(name):\n    return name\n"
    target = _write(tmp_path / "mod.py", original)
    with pytest.raises(ValueError, match="invalid Python"):
        edit_symbol(str(target), "greet", "return (\n")
    assert target.read_text(encoding="utf-8") == original


def test_edit_symbol_creates_missing_top_level(tmp_path: Path) -> None:
    target = _write(tmp_path / "mod.py", "def greet(name):\n    return name\n")
    result = edit_symbol(
        str(target),
        "normalize",
        "def normalize(text):\n    return (text or '').strip().lower()\n",
    )
    text = target.read_text(encoding="utf-8")
    assert result["created"] is True
    assert "def greet(name):" in text
    assert "def normalize(text):" in text
    assert "strip().lower()" in text


def test_edit_symbol_rejects_unchanged_body(tmp_path: Path) -> None:
    original = "def greet(name):\n    return name\n"
    target = _write(tmp_path / "mod.py", original)
    with pytest.raises(ValueError, match="file unchanged"):
        edit_symbol(str(target), "greet", "return name")
    assert target.read_text(encoding="utf-8") == original


def test_edit_symbol_ambiguous_name(tmp_path: Path) -> None:
    target = _write(
        tmp_path / "mod.py",
        "def greet(name):\n    return name\n\n"
        "class A:\n"
        "    def greet(self, name):\n"
        "        return name\n",
    )
    with pytest.raises(ValueError, match="ambiguous"):
        edit_symbol(str(target), "greet", "return 1")
    edit_symbol(str(target), "A.greet", "return 'ok'")
    assert "return 'ok'" in target.read_text(encoding="utf-8")


def test_edit_symbol_expands_same_line_def(tmp_path: Path) -> None:
    target = _write(tmp_path / "mod.py", "def greet(name): return name\n")
    edit_symbol(str(target), "greet", "return f'Hello, {name}!'")
    text = target.read_text(encoding="utf-8")
    assert "def greet(name):" in text
    assert "return f'Hello, {name}!'" in text
    assert "return name" not in text
