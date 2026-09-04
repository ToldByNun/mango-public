"""User-confirm gate for destructive / privileged tool actions (shell, pip).

Uses AgentTaskQueue when mango_agent is available; otherwise in-memory only.
Public API (request_confirm / resolve_confirm / set_confirm_emitter) unchanged.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Callable

EmitFn = Callable[[str, dict[str, Any]], None]

_lock = threading.Lock()
_pending: dict[str, threading.Event] = {}
_results: dict[str, bool] = {}
_emit: EmitFn | None = None
_default_timeout_s = 120.0


def _queue():
    try:
        from mango_agent.agent_task_queue import get_agent_task_queue

        return get_agent_task_queue()
    except Exception:
        return None


def _mark_retry(request_id: str) -> None:
    try:
        from mango_agent.agent_task_queue import mark_retry_side_task

        mark_retry_side_task("confirm", request_id, priority="high")
    except Exception:
        pass


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
    queue = _queue()
    if queue is not None:
        if allowed:
            queue.mark_as_success(request_id)
        else:
            queue.mark_as_failed(request_id, bump_retry=False)
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
        import os

        raw = os.environ.get("MANGO_AUTO_CONFIRM", "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    request_id = str(uuid.uuid4())
    event = threading.Event()
    queue = _queue()
    if queue is not None:
        queue.add(
            {
                "id": request_id,
                "kind": "confirm",
                "confirm_kind": kind,
                "summary": summary,
                "detail": (detail or "")[:2000],
                "status": "pending",
                "priority": "high",
                "retries": 0,
            }
        )
        queue.mark_as_running(request_id)
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
        if queue is not None:
            queue.mark_as_failed(request_id, bump_retry=True)
            _mark_retry(request_id)
        return False

    wait = _default_timeout_s if timeout_s is None else float(timeout_s)
    if not event.wait(timeout=wait):
        with _lock:
            _pending.pop(request_id, None)
            _results.pop(request_id, None)
        if queue is not None:
            queue.mark_as_failed(request_id, bump_retry=True)
            _mark_retry(request_id)
        return False
    with _lock:
        _pending.pop(request_id, None)
        return bool(_results.pop(request_id, False))
