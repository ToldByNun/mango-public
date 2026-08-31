"""Tests for Studio bridge queue + Luau balance helper."""

from __future__ import annotations

import threading
import time

from mango_studio_host.luau_check import balance_ok
from mango_studio_host.studio_bridge import StudioBridge


def test_bridge_roundtrip():
    bridge = StudioBridge(default_timeout_s=5.0)

    def plugin():
        time.sleep(0.05)
        req = bridge.poll(wait_s=2.0)
        assert req is not None
        assert req["tool"] == "rbx_read"
        bridge.complete(req["request_id"], {"ok": True, "source": "print(1)"})

    t = threading.Thread(target=plugin)
    t.start()
    result = bridge.call("rbx_read", {"path": "game.Workspace"}, requires_confirm=False)
    t.join(timeout=3)
    assert result["ok"] is True
    assert result["source"] == "print(1)"


def test_bridge_confirm_deny_timeout():
    bridge = StudioBridge(confirm_timeout_s=0.2)
    result = bridge.call(
        "rbx_delete",
        {"path": "game.Workspace.X"},
        requires_confirm=True,
        confirm_summary="Delete X",
    )
    assert result["ok"] is False
    assert result["error"] == "user_denied"


def test_lease_once():
    bridge = StudioBridge()
    done = threading.Event()

    def caller():
        bridge.call("rbx_tree", {"path": "game"}, timeout_s=2.0)
        done.set()

    threading.Thread(target=caller, daemon=True).start()
    time.sleep(0.05)
    first = bridge.poll(wait_s=1.0)
    second = bridge.poll(wait_s=0.2)
    assert first is not None
    assert second is None  # leased
    bridge.complete(first["request_id"], {"ok": True})
    done.wait(timeout=2)


def test_balance_ok():
    ok, _ = balance_ok('print("hi")')
    assert ok
    bad, detail = balance_ok("function x(")
    assert not bad
    assert "unclosed" in detail or "unbalanced" in detail