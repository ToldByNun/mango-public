"""JSONL client for mango_agent.serve (mirrors Electron Sidecar)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mango_studio_host.paths import (
    find_repo_root,
    prompts_dir,
    python_executable,
    python_package_paths,
    runtime_config_path,
)


EventHandler = Callable[[dict[str, Any]], None]


class SidecarClient:
    """Spawn and talk to `python -m mango_agent.serve` over JSONL stdin/stdout."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        config_path: Path | None = None,
        on_event: EventHandler | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        self.repo_root = repo_root or find_repo_root()
        self.config_path = config_path or runtime_config_path(self.repo_root)
        self.on_event = on_event
        self.extra_env = dict(extra_env or {})
        self._proc: subprocess.Popen[str] | None = None
        self._pending: dict[str, tuple[threading.Event, dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._seq = 0
        self._reader: threading.Thread | None = None
        self._stderr_tail = ""

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.running:
            return
        python = python_executable(self.repo_root)
        package_paths = python_package_paths(self.repo_root)
        path_sep = ";" if sys.platform == "win32" else ":"
        prior = os.environ.get("PYTHONPATH", "")
        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": path_sep.join([*package_paths, prior] if prior else package_paths),
            "MANGO_PROMPTS_DIR": prompts_dir(self.repo_root),
            "MANGO_RUNTIME_CONFIG": str(self.config_path),
            "MANGO_REPO_ROOT": str(self.repo_root),
            **self.extra_env,
        }
        self._stderr_tail = ""
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._proc = subprocess.Popen(
            [python, "-u", "-m", "mango_agent.serve", "--config", str(self.config_path)],
            cwd=str(self.repo_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=creationflags,
        )
        self._reader = threading.Thread(target=self._read_stdout, daemon=True, name="sidecar-stdout")
        self._reader.start()
        threading.Thread(target=self._read_stderr, daemon=True, name="sidecar-stderr").start()
        # Health handshake
        self.request("health", {}, timeout_s=30.0)

    def stop(self) -> None:
        if not self._proc:
            return
        try:
            self.request("shutdown", {}, timeout_s=3.0)
        except Exception:
            pass
        proc = self._proc
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        self._proc = None

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_s: float = 120.0,
    ) -> dict[str, Any]:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("sidecar is not running")
        with self._lock:
            self._seq += 1
            req_id = str(self._seq)
        event = threading.Event()
        slot: dict[str, Any] = {}
        self._pending[req_id] = (event, slot)
        payload = json.dumps({"id": req_id, "method": method, "params": params or {}})
        try:
            self._proc.stdin.write(payload + "\n")
            self._proc.stdin.flush()
        except OSError as exc:
            self._pending.pop(req_id, None)
            raise RuntimeError(f"sidecar write failed: {exc}") from exc

        # run / load_model / cancel: long-lived — wait with large timeout
        wait_s = timeout_s
        if method in {"run", "load_model", "cancel"}:
            wait_s = max(timeout_s, 3600.0)
        if not event.wait(timeout=wait_s):
            self._pending.pop(req_id, None)
            raise TimeoutError(f"sidecar timeout ({method})")
        if slot.get("ok") is False:
            raise RuntimeError(str(slot.get("error") or "sidecar error"))
        result = slot.get("result")
        return result if isinstance(result, dict) else {}

    def _read_stdout(self) -> None:
        proc = self._proc
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            trimmed = line.strip()
            if not trimmed:
                continue
            try:
                message = json.loads(trimmed)
            except json.JSONDecodeError:
                continue
            if isinstance(message.get("event"), str):
                if self.on_event:
                    try:
                        self.on_event(message)
                    except Exception:
                        pass
                continue
            req_id = str(message.get("id") or "")
            pending = self._pending.pop(req_id, None)
            if not pending:
                continue
            event, slot = pending
            slot["ok"] = message.get("ok", True)
            slot["error"] = message.get("error")
            slot["result"] = message.get("result")
            event.set()

    def _read_stderr(self) -> None:
        proc = self._proc
        if not proc or not proc.stderr:
            return
        for line in proc.stderr:
            text = line.rstrip()
            if text:
                print(f"[sidecar] {text}", file=sys.stderr, flush=True)
                self._stderr_tail = (self._stderr_tail + text)[-4000:]
