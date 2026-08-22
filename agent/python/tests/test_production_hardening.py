"""Production hardening: undo history, workspace jail, watchdog, serve fallback."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from mango_agent.checkpoints import (
    restore_checkpoint,
    snapshot_paths,
    undo_last_mutation,
)


def _ws(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    return workspace


def test_undo_walks_back_through_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MANGO_CHECKPOINTS_DIR", str(tmp_path / "ck"))
    monkeypatch.setenv("MANGO_FILE_CHECKPOINTS", "1")
    workspace = _ws(tmp_path)
    target = workspace / "a.py"
    target.write_text("v1\n", encoding="utf-8")
    snapshot_paths([target], session_id="hist", workspace=workspace)
    target.write_text("v2\n", encoding="utf-8")
    snapshot_paths([target], session_id="hist", workspace=workspace)
    target.write_text("v3\n", encoding="utf-8")

    consumed: set[str] = set()
    first = undo_last_mutation(session_id="hist", workspace=workspace, consumed=consumed)
    assert first["ok"] is True
    assert target.read_text(encoding="utf-8") == "v2\n"

    second = undo_last_mutation(session_id="hist", workspace=workspace, consumed=consumed)
    assert second["ok"] is True
    assert target.read_text(encoding="utf-8") == "v1\n"

    third = undo_last_mutation(session_id="hist", workspace=workspace, consumed=consumed)
    assert third["ok"] is False


def test_restore_deleted_parent_chain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MANGO_CHECKPOINTS_DIR", str(tmp_path / "ck"))
    monkeypatch.setenv("MANGO_FILE_CHECKPOINTS", "1")
    workspace = _ws(tmp_path)
    nested = workspace / "pkg" / "sub"
    nested.mkdir(parents=True)
    target = nested / "mod.py"
    target.write_text("ok = True\n", encoding="utf-8")
    info = snapshot_paths([target], session_id="deep", workspace=workspace)
    assert info is not None

    # Simulate the model deleting the whole tree.
    import shutil

    shutil.rmtree(workspace / "pkg")
    restored = restore_checkpoint(info.checkpoint_id, session_id="deep", workspace=workspace)
    assert "pkg/sub/mod.py" in restored
    assert target.read_text(encoding="utf-8") == "ok = True\n"


def test_snapshot_same_paths_same_second_unique_ids(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MANGO_CHECKPOINTS_DIR", str(tmp_path / "ck"))
    monkeypatch.setenv("MANGO_FILE_CHECKPOINTS", "1")
    workspace = _ws(tmp_path)
    target = workspace / "same.txt"
    target.write_text("1\n", encoding="utf-8")
    first = snapshot_paths([target], session_id="uniq", workspace=workspace)
    target.write_text("2\n", encoding="utf-8")
    second = snapshot_paths([target], session_id="uniq", workspace=workspace)
    assert first is not None and second is not None
    assert first.checkpoint_id != second.checkpoint_id


def test_relative_paths_anchor_to_last_read_dir(tmp_path: Path) -> None:
    from mango_tools.paths import resolve_tool_path

    project = tmp_path / "proj"
    project.mkdir()
    target = project / "message.txt"
    target.write_text("Hello Mango\n", encoding="utf-8")

    # No workspace declared; the model read an absolute path, then uses a bare name.
    context = {"last_read_dir": str(project)}
    assert resolve_tool_path("message.txt", context) == target.resolve()
    # Unknown relative names fall back to the anchored directory as the target.
    fallback = resolve_tool_path("other.txt", context)
    assert fallback.parent == project.resolve()


def test_write_file_jail(tmp_path: Path) -> None:
    from mango_tools.implementations.write_file import write_file

    workspace = _ws(tmp_path)
    context = {"workspace": str(workspace), "enforce_jail": True}
    out = write_file("inside.txt", "hello\n", _context=context)
    assert (workspace / "inside.txt").read_text(encoding="utf-8") == "hello\n"
    assert out["path"] == "inside.txt"

    outside = tmp_path / "outside.txt"
    with pytest.raises(PermissionError):
        write_file(str(outside), "evil\n", _context=context)
    assert not outside.exists()

    # Without an enforced jail (bare library use), absolute paths stay allowed.
    legacy = write_file(str(outside), "ok\n", _context={"workspace": str(workspace)})
    assert outside.read_text(encoding="utf-8") == "ok\n"
    assert legacy["absolute_path"] == str(outside.resolve())


def test_edit_file_jail(tmp_path: Path) -> None:
    from mango_tools.implementations.edit_file import edit_file

    workspace = _ws(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("a = 1\n", encoding="utf-8")
    with pytest.raises(PermissionError):
        edit_file(
            str(victim),
            "a",
            "b",
            _context={"workspace": str(workspace), "enforce_jail": True},
        )


def test_delete_file_jail(tmp_path: Path) -> None:
    from mango_tools.implementations.delete_file import delete_file

    workspace = _ws(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("x\n", encoding="utf-8")
    with pytest.raises(PermissionError):
        delete_file(str(victim), _context={"workspace": str(workspace), "enforce_jail": True})
    assert victim.exists()


def test_watchdog_aborts_stalled_stream(monkeypatch) -> None:
    from mango_runtime import model_runner as mr

    monkeypatch.setattr(mr, "TOKEN_GAP_TIMEOUT_S", 0.2)

    class FakeStream:
        def __iter__(self):
            yield {"choices": [{"text": "tok"}]}
            time.sleep(0.5)
            yield {"choices": [{"text": "tok"}]}

        def close(self) -> None:
            pass

    class FakeLlama:
        def create_completion(self, **_kwargs):
            return FakeStream()

        def tokenize(self, text: bytes, add_bos: bool = False):
            return list(text)

    runner = mr.ModelRunner.__new__(mr.ModelRunner)
    runner._llama = FakeLlama()
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        runner._stream_completion(FakeLlama(), "p", {}, None)
    assert time.monotonic() - started < 5


def test_watchdog_passes_healthy_stream() -> None:
    from mango_runtime import model_runner as mr

    class FakeStream:
        def __iter__(self):
            for chunk in ("a", "b", "c"):
                yield {"choices": [{"text": chunk}]}

        def close(self) -> None:
            pass

    class FakeLlama:
        def create_completion(self, **_kwargs):
            return FakeStream()

        def tokenize(self, text: bytes, add_bos: bool = False):
            return list(text)

    runner = mr.ModelRunner.__new__(mr.ModelRunner)
    runner._llama = FakeLlama()
    text, choice, usage, _timing = runner._stream_completion(FakeLlama(), "p", {}, None)
    assert text == "abc"


def test_thought_should_stop_after_closed_think_block() -> None:
    """Mango-1 closes its reasoning early; the tool tail must fire then."""
    from mango_runtime.model_runner import thought_should_stop

    open_think = "<think>Plan: read file, then patch it. Still deciding..."
    closed_think = "<think>Plan: read main.py, then fix item key.</think>"
    assert not thought_should_stop(open_think + " " * 80, force_grammar=True), (
        "open think block must keep streaming"
    )
    assert thought_should_stop(closed_think + " padding to satisfy min length", force_grammar=True), (
        "closed think block must stop the thought phase"
    )
    assert not thought_should_stop(open_think, force_grammar=False), (
        "without forced grammar the thought phase is never cut"
    )
    call = closed_think + '\n<tool_call=read_file : {"path": "main.py"}>'
    assert thought_should_stop(call, force_grammar=True), (
        "a parseable tool call must stop the phase immediately"
    )
