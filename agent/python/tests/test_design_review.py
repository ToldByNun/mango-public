from __future__ import annotations

from mango_agent.design_review import (
    coarsen_after_read_message,
    has_per_client_locks,
    has_single_global_lock,
    lock_coarsened,
    review_message,
)

_PER_CLIENT = """
from collections import defaultdict
from threading import Lock

class SlidingWindowLimiter:
    def __init__(self, max_requests, window_seconds):
        self.locks = defaultdict(Lock)
        self.clients = defaultdict(list)

    def allow(self, client_id):
        with self.locks[client_id]:
            self.clients[client_id].append(0)
            return True
"""

_GLOBAL = """
from collections import defaultdict
from threading import Lock

class SlidingWindowLimiter:
    def __init__(self, max_requests, window_seconds):
        self.lock = Lock()
        self.clients = defaultdict(list)

    def allow(self, client_id):
        with self.lock:
            self.clients[client_id].append(0)
            return True
"""


def test_detects_per_client_and_global_lock() -> None:
    assert has_per_client_locks(_PER_CLIENT)
    assert not has_single_global_lock(_PER_CLIENT)
    assert has_single_global_lock(_GLOBAL)
    assert not has_per_client_locks(_GLOBAL)


def test_lock_coarsened_from_per_client_to_global() -> None:
    assert lock_coarsened(_PER_CLIENT, _GLOBAL)
    assert not lock_coarsened(_GLOBAL, _PER_CLIENT)
    assert not lock_coarsened("", _GLOBAL)
    assert not lock_coarsened(_PER_CLIENT, _PER_CLIENT)


def test_review_messages_name_the_trap() -> None:
    assert "per-client" in review_message(coarsened=True).lower()
    assert "read_file" in review_message(coarsened=False)
    assert "global lock" in coarsen_after_read_message().lower()
