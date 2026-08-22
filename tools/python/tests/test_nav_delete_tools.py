"""A2: delete/list/glob tools + catalog sync."""

from __future__ import annotations

from pathlib import Path

import pytest

from mango_tools.catalog import CATALOG, alias_map, required_keys_map
from mango_tools.gbnf import _REQUIRED_KEYS, tool_call_gbnf
from mango_tools.implementations import create_default_registry
from mango_tools.implementations.delete_file import delete_file
from mango_tools.implementations.glob_files import glob_files
from mango_tools.implementations.list_dir import list_dir


def test_list_dir_and_glob(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("y\n", encoding="utf-8")
    ctx = {"workspace": str(tmp_path)}
    listed = list_dir(".", _context=ctx)
    assert listed["count"] >= 2
    names = {item["name"] for item in listed["entries"]}
    assert "a.py" in names
    assert "sub" in names
    found = glob_files("**/*.py", path=".", _context=ctx)
    assert "a.py" in found["matches"]


def test_delete_file_and_jail(tmp_path: Path) -> None:
    target = tmp_path / "gone.txt"
    target.write_text("bye\n", encoding="utf-8")
    ctx = {"workspace": str(tmp_path)}
    result = delete_file(str(target), _context=ctx)
    assert result["deleted"] is True
    assert not target.exists()
    outside = Path.home() / ".mango_delete_jail_probe.txt"
    outside.write_text("nope\n", encoding="utf-8")
    try:
        with pytest.raises(PermissionError):
            delete_file(str(outside), _context=ctx)
    finally:
        if outside.exists():
            outside.unlink()


def test_registry_includes_nav_tools(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_DELETE_TOOL", "1")
    monkeypatch.setenv("MANGO_FILE_CHECKPOINTS", "1")
    registry = create_default_registry(enable_delete=True)
    names = {schema.name for schema in registry.schemas()}
    assert "list_dir" in names
    assert "glob_files" in names
    assert "delete_file" in names


def test_catalog_sync_with_gbnf_and_registry(monkeypatch) -> None:
    monkeypatch.setenv("MANGO_DELETE_TOOL", "1")
    registry = create_default_registry(enable_delete=True)
    registered = {schema.name for schema in registry.schemas()}
    # Every registered tool that is in the catalog must share required keys with GBNF.
    required = required_keys_map()
    for name in registered:
        if name not in CATALOG:
            continue
        assert name in _REQUIRED_KEYS
        assert tuple(_REQUIRED_KEYS[name]) == tuple(required[name]) or name == "write_file"
    # Aliases resolve to catalog names.
    aliases = alias_map()
    assert aliases["ls"] == "list_dir"
    assert aliases["rm"] == "delete_file"
    grammar = tool_call_gbnf(["list_dir", "glob_files", "delete_file"], schemas=registry.schemas())
    assert "list_dir" in grammar
    assert "glob_files" in grammar
    assert "delete_file" in grammar
