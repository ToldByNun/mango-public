"""JSONL sidecar for the Electron UI: python -m mango_agent.serve --config path."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, TextIO

from mango_agent.agent_context import AgentLimits
from mango_agent.thinking import thinking_preset
from mango_agent.orchestrator import Orchestrator
from mango_agent.prompt import render_system_prompt
from mango_runtime.config import load_config, resolve_config_path


class ServeError(Exception):
    pass


def is_mango_source_tree(path: str | Path) -> bool:
    """True when `path` is the Mango repo itself (unsafe as an agent workspace)."""
    root = Path(path).expanduser().resolve()
    return (
        (root / "runtime" / "config.yaml").is_file()
        and (root / "agent" / "python" / "mango_agent").is_dir()
        and (root / "apps" / "electron").is_dir()
    )


def resolve_run_workspace(requested: str, session_id: str = "") -> Path:
    """Use the requested folder unless it is the Mango source tree."""
    raw = (requested or "").strip()
    if raw:
        path = Path(raw).expanduser().resolve()
        if path.is_dir() and not is_mango_source_tree(path):
            print(f"[mango] using workspace={path}", file=sys.stderr, flush=True)
            return path
        if is_mango_source_tree(path):
            print(f"[mango] rejected Mango source tree as workspace={path}", file=sys.stderr, flush=True)
    dest = Path.home() / ".mango" / "workspaces" / (session_id or "default")
    dest.mkdir(parents=True, exist_ok=True)
    print(f"[mango] fallback workspace={dest}", file=sys.stderr, flush=True)
    return dest


def _tools_fingerprint() -> dict[str, Any]:
    """Expose tool module versions for stale-sidecar detection."""
    import hashlib
    import importlib

    run_tests_mod = importlib.import_module("mango_tools.implementations.run_tests")
    run_tests_path = Path(run_tests_mod.__file__).resolve()
    digest = hashlib.sha256(run_tests_path.read_bytes()).hexdigest()[:12]
    return {
        "run_tests_timeout_s": run_tests_mod._TEST_TIMEOUT_SECONDS,
        "run_tests_file": str(run_tests_path),
        "run_tests_sha256_12": digest,
    }


class AgentServer:
    def __init__(self, config_path: str | Path | None, out: TextIO) -> None:
        self._config_path = resolve_config_path(config_path)
        self._out = out
        self._out_lock = threading.Lock()
        self._runner: Any | None = None
        self._agent_lock = threading.Lock()
        self._busy = False
        self._current_agent: Any | None = None
        self._run_thread: threading.Thread | None = None
        self._session_id = ""

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        method = str(message.get("method") or "")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "health":
            return {
                "status": "ok",
                "busy": self._busy,
                "model_loaded": self._runner is not None,
                **_tools_fingerprint(),
            }
        if method == "load_model":
            return self._load_model()
        if method == "get_settings":
            return self._get_settings()
        if method == "set_model_path":
            return self._set_model_path(str(params.get("path") or ""))
        if method == "run":
            return self._start_run(params)
        if method == "generate_title":
            return self._generate_title_request(params)
        if method == "cancel":
            return self._cancel()
        if method == "shutdown":
            return self._begin_shutdown()
        raise ServeError(f"unknown method {method}")

    def emit(self, event: str, payload: dict[str, Any] | None = None) -> None:
        line = {
            "event": event,
            "session_id": self._session_id,
            "payload": payload or {},
        }
        self._write(line)

    def _write(self, obj: dict[str, Any]) -> None:
        blob = json.dumps(obj, ensure_ascii=False)
        with self._out_lock:
            self._out.write(blob + "\n")
            self._out.flush()

    def _load_model(self) -> dict[str, Any]:
        from mango_runtime import ModelRunner

        if self._runner is None:
            runner = ModelRunner(str(self._config_path))
            runner.load()
            self._runner = runner
        config = load_config(self._config_path)
        return {
            "status": "loaded",
            "model_path": config.model.path,
            "n_ctx": config.model.n_ctx,
        }

    def _get_settings(self) -> dict[str, Any]:
        config = load_config(self._config_path)
        name = Path(config.model.path).stem.replace("-", " ")
        return {
            "model_path": config.model.path,
            "model_name": name or "Local model",
            "temperature": config.inference.temperature,
            "top_p": config.inference.top_p,
            "n_ctx": config.model.n_ctx,
        }

    def _set_model_path(self, model_path: str) -> dict[str, Any]:
        if not model_path.strip():
            raise ServeError("model path is empty")
        path = Path(model_path).expanduser()
        if not path.is_file():
            raise ServeError(f"model file not found: {model_path}")
        text = self._config_path.read_text(encoding="utf-8")
        escaped = "'" + str(path).replace("'", "''") + "'"
        updated, count = re.subn(
            r"(path:\s*)(\"[^\"]*\"|'[^']*')",
            lambda m, replacement=escaped: m.group(1) + replacement,
            text,
            count=1,
        )
        if count == 0:
            raise ServeError("could not find model.path in config.yaml")
        self._config_path.write_text(updated, encoding="utf-8")
        runner = self._runner
        self._runner = None
        if runner is not None:
            unload = getattr(runner, "unload", None)
            if callable(unload):
                unload(timeout_s=4.0)
        return {"model_path": str(path)}

    def _fallback_title(self, goal: str) -> str:
        line = " ".join(goal.split()).strip()
        if len(line) <= 42:
            return line or "New agent"
        return f"{line[:41]}…"

    def _clean_generated_title(self, raw: str) -> str:
        text = raw.strip().strip("\"'").strip()
        if not text:
            return ""
        text = text.splitlines()[0].strip()
        if text.lower().startswith("title:"):
            text = text[6:].strip()
        text = text.rstrip(".")
        if len(text) > 48:
            text = f"{text[:47]}…"
        return text

    def _generate_title(self, goal: str) -> str:
        if self._runner is None:
            self._load_model()
        snippet = goal.strip()[:600]
        prompt = render_system_prompt("title", goal=snippet)
        result = self._runner.complete(
            prompt,
            max_tokens=24,
            temperature=0.2,
            reset_cache=True,
        )
        title = self._clean_generated_title(str(result.text or ""))
        return title or self._fallback_title(goal)

    def _generate_title_request(self, params: dict[str, Any]) -> dict[str, Any]:
        goal = str(params.get("goal") or "")
        if not goal.strip():
            raise ServeError("goal is empty")
        title = self._generate_title(goal)
        return {"title": title}

    def _start_run(self, params: dict[str, Any]) -> dict[str, Any]:
        with self._agent_lock:
            if self._busy:
                raise ServeError("agent is busy")
            self._busy = True
        self._session_id = str(params.get("session_id") or "")
        workspace = resolve_run_workspace(str(params.get("workspace") or ""), self._session_id)
        goal = str(params.get("goal") or "")
        thinking_level = str(params.get("thinking_level") or "off")
        if not goal.strip():
            self._busy = False
            raise ServeError("goal is empty")
        if bool(params.get("generate_title")):
            try:
                title = self._generate_title(goal)
            except Exception as exc:  # noqa: BLE001
                print(f"[mango] title generation failed: {exc}", file=sys.stderr, flush=True)
                title = self._fallback_title(goal)
            if title:
                self.emit("agent.title", {"title": title})
        thread = threading.Thread(
            target=self._run,
            args=(str(workspace), goal, thinking_level),
            daemon=True,
            name="agent-run",
        )
        self._run_thread = thread
        thread.start()
        return {"status": "started", "session_id": self._session_id, "workspace": str(workspace)}

    def _run(self, workspace: str, goal: str, thinking_level: str = "off") -> None:
        try:
            if self._runner is None:
                self._load_model()
            preset = thinking_preset(thinking_level)
            print(
                f"[mango] agent loop workspace={workspace} thinking={preset.level}",
                file=sys.stderr,
                flush=True,
            )
            orch = Orchestrator(
                self._runner,
                workspace=workspace,
                limits=AgentLimits(
                    max_iterations=20,
                    max_runtime_seconds=900,
                    max_prompt_chars=24_000,
                    max_reasoning_cycles=preset.max_reasoning_cycles,
                    max_epistemic_iterations=8,
                ),
                max_tokens=4096,
                on_event=self._on_agent_event,
                require_tools=True,
                plan_apis_first=True,
                task_wants_tests=True,
                thought_max_tokens=preset.thought_max_tokens,
                tool_max_tokens=2048,
                thinking_level=preset.level,
            )
            self._current_agent = orch.agent
            result = orch.run(goal)
            self.emit(
                "agent.stopped",
                {
                    "reason": result.stop_reason.value,
                    "error": result.error,
                    "iterations": result.iterations,
                },
            )
        except Exception as exc:  # noqa: BLE001
            self.emit("agent.error", {"text": str(exc)})
            self.emit("agent.stopped", {"reason": "error", "error": str(exc)})
        finally:
            self._current_agent = None
            self._run_thread = None
            self._busy = False

    def _on_agent_event(self, message: dict[str, Any]) -> None:
        event = str(message.get("event") or "")
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        if event == "agent.stopped":
            return
        self.emit(event, payload)

    def _cancel(self) -> dict[str, Any]:
        agent = self._current_agent
        if agent is not None:
            agent.cancel()
        return {"status": "cancelling"}

    def _begin_shutdown(self) -> dict[str, Any]:
        self._cancel()
        return {"status": "bye"}

    def _join_run(self, timeout_s: float = 2.0) -> None:
        thread = self._run_thread
        if thread is None or not thread.is_alive():
            return
        if threading.current_thread() is thread:
            return
        thread.join(timeout=timeout_s)

    def _unload_runner(self, *, timeout_s: float = 4.0) -> None:
        runner = self._runner
        self._runner = None
        if runner is None:
            return
        unload = getattr(runner, "unload", None)
        if callable(unload):
            unload(timeout_s=timeout_s)

    def exit_process(self) -> None:
        """Cancel → join run → unload model → exit. CUDA free is timed."""
        self._cancel()
        self._join_run(2.0)
        self._unload_runner(timeout_s=4.0)
        os._exit(0)


def serve_loop(server: AgentServer, inp: TextIO, out: TextIO) -> None:
    for raw in inp:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            server._write({"id": None, "ok": False, "error": f"invalid json: {exc}"})
            continue
        ident = message.get("id")
        try:
            result = server.handle(message)
            server._write({"id": ident, "ok": True, "result": result})
        except ServeError as exc:
            server._write({"id": ident, "ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            server._write({"id": ident, "ok": False, "error": str(exc)})
        if message.get("method") == "shutdown":
            server.exit_process()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mango agent JSONL sidecar")
    parser.add_argument("--config", help="Path to runtime config.yaml")
    args = parser.parse_args(argv)
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    server = AgentServer(args.config, sys.stdout)
    serve_loop(server, sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
