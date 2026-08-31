"""Tests for rbx_* tool caps (no Studio required)."""

from __future__ import annotations

from mango_tools.implementations import roblox_tools as rt


def test_edit_too_large(monkeypatch):
    monkeypatch.setattr(rt, "_EDIT_MAX_CHARS", 10)
    out = rt.rbx_edit("game.X", "a" * 20, "b")
    assert out["ok"] is False
    assert out["error"] == "edit_too_large"


def test_seed_too_large(monkeypatch):
    monkeypatch.setattr(rt, "_CREATE_SEED_MAX_CHARS", 5)
    out = rt.rbx_create("game.SSS", "Script", source="print(123456)")
    assert out["ok"] is False
    assert out["error"] == "seed_too_large"


def test_delete_always_confirm(monkeypatch):
    seen = {}

    def fake(tool, args, *, requires_confirm=False, confirm_summary="", timeout_s=None):
        seen["requires_confirm"] = requires_confirm
        seen["summary"] = confirm_summary
        return {"ok": False, "error": "user_denied"}

    monkeypatch.setattr(rt, "dispatch_studio_tool", fake)
    out = rt.rbx_delete("game.Workspace.Part")
    assert seen["requires_confirm"] is True
    assert out["error"] == "user_denied"


def test_prop_bulk_confirm(monkeypatch):
    seen = {}

    def fake(tool, args, *, requires_confirm=False, confirm_summary="", timeout_s=None):
        seen["requires_confirm"] = requires_confirm
        return {"ok": True}

    monkeypatch.setattr(rt, "dispatch_studio_tool", fake)
    rt.rbx_prop(paths=["a", "b"], property_name="Name", value="x", _context={"confirm_prop_threshold": 1})
    assert seen["requires_confirm"] is True
    seen.clear()
    rt.rbx_prop(path="a", property_name="Name", value="x", _context={"confirm_prop_threshold": 1})
    assert seen["requires_confirm"] is False
