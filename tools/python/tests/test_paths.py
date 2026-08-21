from __future__ import annotations

from pathlib import Path

from mango_tools.paths import normalize_tool_path, resolve_tool_path


def test_normalize_tool_path_strips_user_prefix() -> None:
    assert normalize_tool_path("user/math_utils.py") == "math_utils.py"
    assert normalize_tool_path("/user/test_math_utils.py") == "test_math_utils.py"
    assert normalize_tool_path("workspace/pkg/mod.py") == "pkg/mod.py"


def test_normalize_tool_path_strips_home_user_prefix() -> None:
    assert normalize_tool_path("home/user/math_utils.py") == "math_utils.py"
    assert normalize_tool_path("/home/user/test_math_utils.py") == "test_math_utils.py"


def test_resolve_tool_path_maps_user_prefix_to_workspace(tmp_path: Path) -> None:
    resolved = resolve_tool_path("user/math_utils.py", {"workspace": str(tmp_path)})
    assert resolved == (tmp_path / "math_utils.py").resolve()


def test_resolve_tool_path_maps_home_user_to_workspace_root(tmp_path: Path) -> None:
    resolved = resolve_tool_path("home/user/math_utils.py", {"workspace": str(tmp_path)})
    assert resolved == (tmp_path / "math_utils.py").resolve()


def test_resolve_tool_path_keeps_real_src_layout(tmp_path: Path) -> None:
    target = tmp_path / "src" / "_pytest" / "rewrite.py"
    target.parent.mkdir(parents=True)
    target.write_text("ok", encoding="utf-8")
    resolved = resolve_tool_path("src/_pytest/rewrite.py", {"workspace": str(tmp_path)})
    assert resolved == target.resolve()


def test_resolve_tool_path_still_maps_fake_src_prefix(tmp_path: Path) -> None:
    target = tmp_path / "math_utils.py"
    target.write_text("ok", encoding="utf-8")
    resolved = resolve_tool_path("src/math_utils.py", {"workspace": str(tmp_path)})
    assert resolved == target.resolve()
