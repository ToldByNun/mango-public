from __future__ import annotations

from pathlib import Path

from mango_cli.paths import (
    ensure_workspace_config,
    find_repo_root,
    mango_dir,
    resolve_cli_config,
    runtime_config_path,
    workspace_config_path,
)


def test_find_repo_root() -> None:
    root = find_repo_root(Path(__file__).resolve().parents[3])
    assert root is not None
    assert (root / "agent" / "python").is_dir()
    assert (root / "runtime" / "config.yaml").is_file() or (root / "runtime").is_dir()


def test_runtime_config_default() -> None:
    root = find_repo_root(Path(__file__).resolve().parents[3])
    path = runtime_config_path(root)
    assert path.name in {"config.yaml", "config.yml", "config.example.yaml"}


def test_theme_file_shipped() -> None:
    tcss = Path(__file__).resolve().parents[1] / "mango_cli" / "theme.tcss"
    assert tcss.is_file()
    text = tcss.read_text(encoding="utf-8")
    assert "#e8943a" in text


def test_ensure_workspace_config_creates_mango_dir(tmp_path: Path) -> None:
    seed = tmp_path / "seed.yaml"
    seed.write_text("model:\n  path: 'C:\\\\models\\\\mango.gguf'\n", encoding="utf-8")
    dest = ensure_workspace_config(tmp_path / "proj", seed=seed)
    assert dest == workspace_config_path(tmp_path / "proj")
    assert dest.is_file()
    assert "mango.gguf" in dest.read_text(encoding="utf-8")
    assert mango_dir(tmp_path / "proj").is_dir()


def test_resolve_cli_config_reuses_existing(tmp_path: Path) -> None:
    dest = workspace_config_path(tmp_path)
    dest.parent.mkdir(parents=True)
    dest.write_text("model:\n  path: existing\n", encoding="utf-8")
    again = resolve_cli_config(tmp_path)
    assert again == dest
    assert dest.read_text(encoding="utf-8").count("existing") == 1


def test_migrates_legacy_devdeck_config(tmp_path: Path) -> None:
    legacy = tmp_path / ".devdeck" / "config.yaml"
    legacy.parent.mkdir()
    legacy.write_text("model:\n  path: legacy-gguf\n", encoding="utf-8")
    dest = ensure_workspace_config(tmp_path, seed=None)
    assert dest.is_file()
    assert "legacy-gguf" in dest.read_text(encoding="utf-8")
