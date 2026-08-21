from __future__ import annotations

import subprocess
from pathlib import Path

from mango_codeintel import CodeIndex


def _write_repo(root: Path) -> None:
    (root / "app").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "util.py").write_text(
        "PAD = '" + ("Q" * 400) + "'\n\n"
        "def greet(name):\n"
        "    return f'hi {name}'\n",
        encoding="utf-8",
    )
    (root / "app" / "main.py").write_text(
        "from app.util import greet\n\n"
        "def run():\n"
        "    return greet('world')\n",
        encoding="utf-8",
    )
    (root / "app" / "other.py").write_text(
        "from app.util import greet\n\n"
        "def ping():\n"
        "    greet('x')\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_util.py").write_text(
        "from app.util import greet\n\n"
        "def test_greet():\n"
        "    assert greet('a') == 'hi a'\n",
        encoding="utf-8",
    )


def test_index_definitions_references_and_imports(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    index = CodeIndex(tmp_path)
    stats = index.refresh()
    assert stats["parsed"] >= 3

    defs = index.get_symbol_definition("greet")
    assert any(hit.path.endswith("util.py") and hit.kind == "function" for hit in defs)
    assert any("def greet" in hit.signature for hit in defs)

    refs = index.get_references("greet")
    paths = {hit.path for hit in refs if hit.kind == "call"}
    assert "app/main.py" in paths
    assert "app/other.py" in paths
    assert all(len(hit.snippet) < 80 for hit in refs)

    files = index.get_relevant_files("Wo wird greet aufgerufen")
    assert any(hit.path.startswith("app/") for hit in files)


def test_incremental_refresh_skips_unchanged_files(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    index = CodeIndex(tmp_path)
    first = index.refresh()
    second = index.refresh()
    assert second["skipped"] >= first["parsed"] - 1
    assert second["parsed"] == 0

    (tmp_path / "app" / "util.py").write_text(
        "def greet(name):\n    return name\n\ndef extra():\n    return 1\n",
        encoding="utf-8",
    )
    third = index.refresh()
    assert third["parsed"] >= 1
    names = {hit.name for hit in index.get_symbol_definition("extra")}
    assert "extra" in names


def test_git_snapshot(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True)
    index = CodeIndex(tmp_path)
    index.refresh()
    git = index.query.git_status()
    assert git.available is True
    assert git.recent_commits


def test_lookup_references_query(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    index = CodeIndex(tmp_path)
    payload = index.lookup("Wo wird Funktion greet aufgerufen?")
    assert payload["kind"] == "references"
    assert payload["symbol"] == "greet"
    refs = payload["references"]
    assert any(item["path"].endswith("main.py") for item in refs)
    blob = str(payload)
    assert "Q" * 50 not in blob


def test_impact_graph_includes_importers_and_tests(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    index = CodeIndex(tmp_path)
    payload = index.impact(symbol="greet", path="app/util.py")
    assert "app/main.py" in payload["dependent_files"]
    assert "app/other.py" in payload["dependent_files"]
    assert any(path.endswith("test_util.py") for path in payload["test_files"])
    lookup = index.lookup("What is the impact of changing greet?", kind="impact")
    assert lookup["kind"] == "impact"
    assert lookup["impact"]["test_files"]


def test_slice_file_is_signature_plus_short_body(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    (tmp_path / "app" / "util.py").write_text(
        "PAD = '" + ("Q" * 400) + "'\n\n"
        "def greet(name):\n"
        "    a = 1\n"
        "    b = 2\n"
        "    c = 3\n"
        "    d = 4\n"
        "    e = 5\n"
        "    f = 6\n"
        "    return name\n",
        encoding="utf-8",
    )
    index = CodeIndex(tmp_path)
    index.refresh()
    sliced = index.slice_file("app/util.py", focus_symbols=("greet",))
    assert "def greet" in sliced
    assert "e = 5" in sliced
    assert "f = 6" not in sliced
    assert "Q" * 50 not in sliced
