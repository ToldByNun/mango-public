"""Prioritized durable task queue with crash-recovery and exponential backoff."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

from mango_agent.persistence.persistent_store import PersistentStore

TaskStatus = Literal["pending", "running", "success", "failed"]
TaskPriority = Literal["high", "normal", "low"]

PRIORITY_RANK: dict[str, int] = {"high": 0, "normal": 1, "low": 2}
MAX_BACKOFF_MS = 60_000


def compute_backoff_ms(retries: int) -> int:
    n = max(0, int(retries))
    return min(1000 * (2**n), MAX_BACKOFF_MS)


class TaskQueue:
    def __init__(
        self,
        *,
        file_path: str | Path,
        debounce_s: float = 1.0,
        scope: str = "task-queue",
    ) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._store = PersistentStore[list[dict[str, Any]]](
            file_path=file_path,
            debounce_s=debounce_s,
            scope=scope,
            empty_state=list,
            serialize=lambda tasks: tasks,
            deserialize=lambda raw: list(raw) if isinstance(raw, list) else None,
            recover=lambda tasks: [self._recover_task(t) for t in tasks if isinstance(t, dict)],
        )

    def load_from_storage(self) -> None:
        tasks = self._store.load_from_storage()
        self._items.clear()
        for task in tasks:
            task_id = str(task.get("id") or "")
            if task_id:
                self._items[task_id] = task

    def add(self, task: dict[str, Any]) -> dict[str, Any]:
        next_task = dict(task)
        next_task.setdefault("retries", 0)
        next_task["updated_at"] = int(time.time() * 1000)
        task_id = str(next_task.get("id") or "")
        if not task_id:
            raise ValueError("task.id is required")
        self._items[task_id] = next_task
        self._sync_store()
        return next_task

    def add_batch(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.add(task) for task in tasks]

    def mark_as_pending(self, task_id: str) -> dict[str, Any] | None:
        return self._mark_as(task_id, "pending")

    def mark_as_running(self, task_id: str) -> dict[str, Any] | None:
        return self._mark_as(task_id, "running")

    def mark_as_success(self, task_id: str) -> dict[str, Any] | None:
        return self._mark_as(task_id, "success")

    def mark_as_failed(self, task_id: str, *, bump_retry: bool = True) -> dict[str, Any] | None:
        task = self._items.get(task_id)
        if task is None:
            return None
        task["status"] = "failed"
        if bump_retry:
            task["retries"] = int(task.get("retries") or 0) + 1
        task["updated_at"] = int(time.time() * 1000)
        self._items[task_id] = task
        self._sync_store()
        return task

    def get(self, task_id: str) -> dict[str, Any] | None:
        return self._items.get(task_id)

    def get_all(self) -> list[dict[str, Any]]:
        return list(self._items.values())

    def get_pending(self) -> list[dict[str, Any]]:
        return self.get_by_status("pending")

    def get_by_status(self, status: TaskStatus) -> list[dict[str, Any]]:
        tasks = [t for t in self.get_all() if t.get("status") == status]
        tasks.sort(
            key=lambda t: (
                PRIORITY_RANK.get(str(t.get("priority") or "normal"), 1),
                int(t.get("updated_at") or 0),
            )
        )
        return tasks

    def get_retryable(self, now_ms: int | None = None) -> list[dict[str, Any]]:
        now = int(time.time() * 1000) if now_ms is None else int(now_ms)
        out: list[dict[str, Any]] = []
        for task in self.get_all():
            status = task.get("status")
            if status not in {"failed", "pending"}:
                continue
            retries = int(task.get("retries") or 0)
            if status == "pending" and retries == 0:
                out.append(task)
                continue
            delay = compute_backoff_ms(retries)
            if now - int(task.get("updated_at") or 0) >= delay:
                out.append(task)
        out.sort(
            key=lambda t: (
                PRIORITY_RANK.get(str(t.get("priority") or "normal"), 1),
                int(t.get("updated_at") or 0),
            )
        )
        return out

    def persist_now(self) -> None:
        self._sync_store(immediate=True)

    def destroy(self) -> None:
        self._sync_store(immediate=True)
        self._store.destroy()

    def _mark_as(self, task_id: str, status: TaskStatus) -> dict[str, Any] | None:
        task = self._items.get(task_id)
        if task is None:
            return None
        task["status"] = status
        task["updated_at"] = int(time.time() * 1000)
        self._items[task_id] = task
        self._sync_store()
        return task

    def _recover_task(self, task: dict[str, Any]) -> dict[str, Any]:
        status = str(task.get("status") or task.get("legacy_status") or "pending")
        next_task = dict(task)
        if status in {"running", "uploading"}:
            next_task["status"] = "pending"
            next_task["updated_at"] = int(time.time() * 1000)
        elif status in {"pending", "success", "failed"}:
            next_task["status"] = status
        else:
            next_task["status"] = "pending"
        return next_task

    def _sync_store(self, *, immediate: bool = False) -> None:
        snapshot = self.get_all()
        if immediate:
            self._store.replace_state(snapshot)
            self._store.persist_now()
        else:
            self._store.replace_state(snapshot)
