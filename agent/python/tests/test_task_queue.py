from __future__ import annotations

import json
from pathlib import Path

from mango_agent.persistence.task_queue import TaskQueue, compute_backoff_ms


def test_compute_backoff_caps_at_60s() -> None:
    assert compute_backoff_ms(0) == 1000
    assert compute_backoff_ms(1) == 2000
    assert compute_backoff_ms(2) == 4000
    assert compute_backoff_ms(10) == 60_000


def test_crash_recovery_resets_running(tmp_path: Path) -> None:
    path = tmp_path / "q.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "a",
                    "status": "running",
                    "priority": "high",
                    "retries": 0,
                    "updated_at": 1,
                },
                {
                    "id": "b",
                    "status": "uploading",
                    "priority": "normal",
                    "retries": 0,
                    "updated_at": 1,
                },
            ]
        ),
        encoding="utf-8",
    )
    queue = TaskQueue(file_path=path, debounce_s=0)
    queue.load_from_storage()
    assert queue.get("a")["status"] == "pending"
    assert queue.get("b")["status"] == "pending"


def test_get_retryable_respects_backoff(tmp_path: Path) -> None:
    queue = TaskQueue(file_path=tmp_path / "q.json", debounce_s=0)
    queue.load_from_storage()
    queue.add(
        {
            "id": "r1",
            "kind": "confirm",
            "status": "failed",
            "priority": "high",
            "retries": 2,
        }
    )
    task = queue.get("r1")
    assert task is not None
    # Force updated_at into the past beyond 4s backoff for retries=2
    task["updated_at"] = 0
    queue._items["r1"] = task  # noqa: SLF001
    retryable = queue.get_retryable(now_ms=10_000)
    assert any(t["id"] == "r1" for t in retryable)
