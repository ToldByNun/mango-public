"""Queue for Studio-bound tool calls (plugin long-polls / posts results)."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingStudioCall:
    request_id: str
    tool: str
    args: dict[str, Any]
    requires_confirm: bool = False
    confirm_summary: str = ""
    created_at: float = field(default_factory=time.time)
    leased: bool = False
    event: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None


class StudioBridge:
    """Thread-safe pending-call queue between sidecar tools and the Studio plugin."""

    def __init__(self, *, default_timeout_s: float = 60.0, confirm_timeout_s: float = 120.0) -> None:
        self.default_timeout_s = default_timeout_s
        self.confirm_timeout_s = confirm_timeout_s
        self._lock = threading.Lock()
        self._pending: dict[str, PendingStudioCall] = {}
        self._queue: list[str] = []
        self._wake = threading.Condition(self._lock)

    def call(
        self,
        tool: str,
        args: dict[str, Any],
        *,
        requires_confirm: bool = False,
        confirm_summary: str = "",
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        """Block until the Studio plugin returns a result (or timeout)."""
        request_id = str(uuid.uuid4())
        pending = PendingStudioCall(
            request_id=request_id,
            tool=tool,
            args=dict(args or {}),
            requires_confirm=requires_confirm,
            confirm_summary=confirm_summary or "",
        )
        with self._wake:
            self._pending[request_id] = pending
            self._queue.append(request_id)
            self._wake.notify_all()

        wait = timeout_s
        if wait is None:
            wait = self.confirm_timeout_s if requires_confirm else self.default_timeout_s
        if not pending.event.wait(timeout=wait):
            with self._wake:
                self._pending.pop(request_id, None)
                if request_id in self._queue:
                    self._queue.remove(request_id)
            return {
                "ok": False,
                "error": "user_denied" if requires_confirm else "studio_timeout",
                "detail": f"Studio did not respond within {wait}s",
            }
        result = pending.result or {"ok": False, "error": "empty_result"}
        with self._wake:
            self._pending.pop(request_id, None)
        return result

    def poll(self, *, wait_s: float = 25.0) -> dict[str, Any] | None:
        """Long-poll: lease the next pending tool call (once), or None on timeout."""
        deadline = time.time() + max(0.1, wait_s)
        with self._wake:
            while True:
                for request_id in list(self._queue):
                    pending = self._pending.get(request_id)
                    if pending is None:
                        if request_id in self._queue:
                            self._queue.remove(request_id)
                        continue
                    if pending.leased:
                        continue
                    pending.leased = True
                    return {
                        "request_id": pending.request_id,
                        "tool": pending.tool,
                        "args": pending.args,
                        "requires_confirm": pending.requires_confirm,
                        "confirm_summary": pending.confirm_summary,
                    }
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._wake.wait(timeout=remaining)

    def complete(self, request_id: str, result: dict[str, Any]) -> bool:
        with self._wake:
            pending = self._pending.get(request_id)
            if pending is None:
                return False
            pending.result = dict(result or {})
            if request_id in self._queue:
                self._queue.remove(request_id)
            pending.event.set()
            self._wake.notify_all()
            return True

    def pending_count(self) -> int:
        with self._lock:
            return len(self._queue)
