"""A1: file checkpoint snapshot + restore."""

from __future__ import annotations

from pathlib import Path

from mango_agent.checkpoints import (
    prune_checkpoints,
    restore_checkpoint,
    snapshot_paths,
    undo_last_mutation,
)


def test_snapshot_and_restore_write(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MANGO_CHECKPOINTS_DIR", str(tmp_path / "ck"))
    monkeypatch.setenv("MANGO_FILE_CHECKPOINTS", "1")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "note.txt"
    target.write_text("alpha\n", encoding="utf-8")

    info = snapshot_paths([target], session_id="s1", workspace=workspace)
    assert info is not None
    target.write_text("beta\n", encoding="utf-8")
    restored = restore_checkpoint(info.checkpoint_id, session_id="s1", workspace=workspace)
    assert "note.txt" in restored
    assert target.read_text(encoding="utf-8") == "alpha\n"


def test_undo_last_mutation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MANGO_CHECKPOINTS_DIR", str(tmp_path / "ck"))
    monkeypatch.setenv("MANGO_FILE_CHECKPOINTS", "1")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    snapshot_paths([target], session_id="s2", workspace=workspace)
    target.write_text("x = 2\n", encoding="utf-8")
    result = undo_last_mutation(session_id="s2", workspace=workspace)
    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "x = 1\n"


def test_checkpoint_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MANGO_CHECKPOINTS_DIR", str(tmp_path / "ck"))
    monkeypatch.setenv("MANGO_FILE_CHECKPOINTS", "0")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("x\n", encoding="utf-8")
    assert snapshot_paths([target], session_id="s3", workspace=workspace) is None


def test_prune_caps_entries(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MANGO_CHECKPOINTS_DIR", str(tmp_path / "ck"))
    monkeypatch.setenv("MANGO_FILE_CHECKPOINTS", "1")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "f.txt"
    target.write_text("1\n", encoding="utf-8")
    for i in range(6):
        target.write_text(f"{i}\n", encoding="utf-8")
        snapshot_paths([target], session_id="prune", workspace=workspace)
    prune_checkpoints(session_id="prune", max_entries=3, max_bytes=10_000_000)
    root = tmp_path / "ck" / "prune"
    assert len([p for p in root.iterdir() if p.is_dir()]) <= 3
