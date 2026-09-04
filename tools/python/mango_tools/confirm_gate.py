"""User-confirm gate for destructive / privileged tool actions (shell, pip)."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable

EmitFn = Callable[[str, dict[str, Any]], None]

_lock = threading.Lock()
_pending: dict[str, threading.Event] = {}
_results: dict[str, bool] = {}
_emit: EmitFn | None = None
_default_timeout_s = 120.0


def set_confirm_emitter(emit: EmitFn | None) -> None:
    global _emit
    _emit = emit


def resolve_confirm(request_id: str, allowed: bool) -> bool:
    with _lock:
        event = _pending.get(request_id)
        if event is None:
            return False
        _results[request_id] = bool(allowed)
        event.set()
        return True


def request_confirm(
    *,
    summary: str,
    kind: str = "shell",
    detail: str = "",
    timeout_s: float | None = None,
) -> bool:
    """Block until UI allows/denies. Returns False on deny/timeout/no emitter."""
    emit = _emit
    if emit is None:
        # No UI attached (CLI/tests): deny privileged actions by default unless env override
        import os

        raw = os.environ.get("MANGO_AUTO_CONFIRM", "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    request_id = str(uuid.uuid4())
    event = threading.Event()
    with _lock:
        _pending[request_id] = event
    try:
        emit(
            "agent.confirm",
            {
                "request_id": request_id,
                "kind": kind,
                "summary": summary,
                "detail": (detail or "")[:2000],
            },
        )
    except Exception:
        with _lock:
            _pending.pop(request_id, None)
        return False

    wait = _default_timeout_s if timeout_s is None else float(timeout_s)
    if not event.wait(timeout=wait):
        with _lock:
            _pending.pop(request_id, None)
            _results.pop(request_id, None)
        return False
    with _lock:
        _pending.pop(request_id, None)
        return bool(_results.pop(request_id, False))
