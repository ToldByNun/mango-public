"""Agent-side task queue for confirm / undo / retry side-jobs."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from mango_agent.persistence.task_queue import TaskQueue

_queue: TaskQueue | None = None
_queue_lock = threading.Lock()


def queues_root() -> Path:
    override = os.environ.get("MANGO_QUEUES_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
    else:
        path = Path.home() / ".mango" / "queues"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_agent_task_queue() -> TaskQueue:
    global _queue
    with _queue_lock:
        if _queue is None:
            _queue = TaskQueue(
                file_path=queues_root() / "agent-tasks.json",
                debounce_s=1.0,
                scope="agent-tasks",
            )
            _queue.load_from_storage()
        return _queue


def destroy_agent_task_queue() -> None:
    global _queue
    with _queue_lock:
        if _queue is not None:
            _queue.destroy()
            _queue = None


def record_undo_consumed(session_id: str, checkpoint_id: str, workspace: str = "") -> dict[str, Any]:
    queue = get_agent_task_queue()
    task_id = f"undo:{session_id}:{checkpoint_id}"
    existing = queue.get(task_id)
    if existing:
        return queue.mark_as_success(task_id) or existing
    return queue.add(
        {
            "id": task_id,
            "kind": "undo",
            "session_id": session_id,
            "checkpoint_id": checkpoint_id,
            "workspace": workspace,
            "status": "success",
            "priority": "normal",
            "retries": 0,
        }
    )


def get_undo_consumed(session_id: str) -> set[str]:
    queue = get_agent_task_queue()
    consumed: set[str] = set()
    prefix = f"undo:{session_id}:"
    for task in queue.get_all():
        if not str(task.get("id") or "").startswith(prefix):
            continue
        if task.get("status") != "success":
            continue
        checkpoint_id = str(task.get("checkpoint_id") or "")
        if checkpoint_id:
            consumed.add(checkpoint_id)
    return consumed


def get_undo_workspace(session_id: str) -> str | None:
    queue = get_agent_task_queue()
    meta = queue.get(f"undo-workspace:{session_id}")
    if meta:
        workspace = str(meta.get("workspace") or "").strip()
        if workspace:
            return workspace
    prefix = f"undo:{session_id}:"
    newest: dict[str, Any] | None = None
    for task in queue.get_all():
        if not str(task.get("id") or "").startswith(prefix):
            continue
        if newest is None or int(task.get("updated_at") or 0) > int(newest.get("updated_at") or 0):
            newest = task
    if newest is None:
        return None
    workspace = str(newest.get("workspace") or "").strip()
    return workspace or None


def set_undo_workspace(session_id: str, workspace: str) -> None:
    queue = get_agent_task_queue()
    task_id = f"undo-workspace:{session_id}"
    queue.add(
        {
            "id": task_id,
            "kind": "undo_workspace",
            "session_id": session_id,
            "workspace": workspace,
            "status": "success",
            "priority": "low",
            "retries": 0,
        }
    )


def mark_retry_side_task(kind: str, key: str, *, priority: str = "normal") -> dict[str, Any]:
    """Record a retryable side-task (confirm re-emit / undo retry)."""
    queue = get_agent_task_queue()
    task_id = f"retry:{kind}:{key}"
    existing = queue.get(task_id)
    if existing:
        return queue.mark_as_failed(task_id, bump_retry=True) or existing
    return queue.add(
        {
            "id": task_id,
            "kind": kind,
            "key": key,
            "status": "failed",
            "priority": priority,
            "retries": 1,
        }
    )
