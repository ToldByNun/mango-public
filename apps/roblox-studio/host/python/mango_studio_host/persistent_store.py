"""Debounced JSON settings store for studio host (mirrors mango_agent.persistence)."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


def _debug(scope: str, message: str, detail: Any = None) -> None:
    try:
        line = f"[mango-studio:{scope}] {message}"
        if detail is not None:
            print(line, detail, file=sys.stderr, flush=True)
        else:
            print(line, file=sys.stderr, flush=True)
    except Exception:
        pass


class PersistentStore(Generic[T]):
    def __init__(
        self,
        *,
        file_path: str | Path,
        serialize: Callable[[T], Any],
        deserialize: Callable[[Any], T | None],
        empty_state: Callable[[], T],
        debounce_s: float = 1.0,
        scope: str = "store",
    ) -> None:
        self._file_path = Path(file_path)
        self._serialize = serialize
        self._deserialize = deserialize
        self._empty_state = empty_state
        self._debounce_s = max(0.0, float(debounce_s))
        self._scope = scope
        self._state: T = empty_state()
        self._timer: threading.Timer | None = None
        self._lock = threading.RLock()
        self._destroyed = False

    def get_state(self) -> T:
        with self._lock:
            return self._state

    def replace_state(self, next_state: T) -> None:
        with self._lock:
            self._state = next_state
            self.debounce_persist()

    def load_from_storage(self) -> T:
        with self._lock:
            try:
                if not self._file_path.is_file():
                    self._state = self._empty_state()
                    return self._state
                raw_text = self._file_path.read_text(encoding="utf-8")
                if not raw_text.strip():
                    self._state = self._empty_state()
                    return self._state
                parsed = json.loads(raw_text)
                loaded = self._deserialize(parsed)
                self._state = loaded if loaded is not None else self._empty_state()
                return self._state
            except Exception as exc:  # noqa: BLE001
                _debug(self._scope, "load_from_storage failed", exc)
                self._state = self._empty_state()
                return self._state

    def persist_now(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            try:
                self._file_path.parent.mkdir(parents=True, exist_ok=True)
                payload = json.dumps(self._serialize(self._state), ensure_ascii=False, indent=2)
                tmp = self._file_path.with_suffix(self._file_path.suffix + ".tmp")
                tmp.write_text(payload, encoding="utf-8")
                tmp.replace(self._file_path)
            except Exception as exc:  # noqa: BLE001
                _debug(self._scope, "persist_now failed", exc)

    def debounce_persist(self) -> None:
        with self._lock:
            if self._destroyed:
                return
            if self._debounce_s <= 0:
                self.persist_now()
                return
            if self._timer is not None:
                self._timer.cancel()
            timer = threading.Timer(self._debounce_s, self._persist_from_timer)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def destroy(self) -> None:
        with self._lock:
            self._destroyed = True
            self.persist_now()

    def _persist_from_timer(self) -> None:
        with self._lock:
            self._timer = None
            if self._destroyed:
                return
            self.persist_now()
