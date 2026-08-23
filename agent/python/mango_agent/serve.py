"""JSONL sidecar for the Electron UI: python -m mango_agent.serve --config path."""

from __future__ import annotations

import argparse
import concurrent.futures
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
from mango_runtime.config import load_config, load_config_file, resolve_config_path, save_config
from mango_runtime.gpu_env import detect_gpu_backend, list_ggml_backends
from mango_runtime.types import HardwareConfig, InferenceConfig, ModelConfig, RuntimeConfig


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
        self._runner_lock = threading.RLock()
        self._agent_lock = threading.Lock()
        self._busy = False
        self._current_agent: Any | None = None
        self._run_thread: threading.Thread | None = None
        self._session_id = ""
        # Per-session undo state survives the run so the UI can still revert the
        # last mutation after agent.stopped.
        self._undo_history: dict[str, set[str]] = {}
        self._undo_workspace: dict[str, str] = {}

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
        if method == "update_settings":
            return self._update_settings(params)
        if method == "run":
            return self._start_run(params)
        if method == "generate_title":
            return self._generate_title_request(params)
        if method == "cancel":
            return self._cancel()
        if method == "continue_stall":
            return self._continue_stall()
        if method == "undo_last_mutation":
            return self._undo_last_mutation()
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

        with self._runner_lock:
            if self._runner is None:
                runner = ModelRunner(str(self._config_path))
                runner.load()
                self._runner = runner
                freshly_loaded = True
            else:
                freshly_loaded = False
        config = load_config(self._config_path)
        if freshly_loaded:
            self.emit("model.loaded", {"model_path": config.model.path})
        return {
            "status": "loaded",
            "model_path": config.model.path,
            "n_ctx": config.model.n_ctx,
        }

    def _read_config(self) -> RuntimeConfig:
        return load_config_file(self._config_path, require_model=False)

    def _get_settings(self) -> dict[str, Any]:
        config = self._read_config()
        path = config.model.path.strip()
        name = Path(path).stem.replace("-", " ") if path else ""
        return {
            "model_path": path,
            "model_name": name or "Local model",
            "temperature": config.inference.temperature,
            "top_p": config.inference.top_p,
            "max_tokens": config.inference.max_tokens,
            "n_ctx": config.model.n_ctx,
            "n_batch": config.model.n_batch,
            "n_gpu_layers": config.hardware.n_gpu_layers,
            "n_threads": config.hardware.n_threads,
            "gpu_backend": detect_gpu_backend(),
            "registered_backends": list_ggml_backends(),
            "config_path": str(self._config_path),
        }

    def _set_model_path(self, model_path: str) -> dict[str, Any]:
        if not model_path.strip():
            raise ServeError("model path is empty")
        path = Path(model_path).expanduser()
        if not path.is_file():
            raise ServeError(f"model file not found: {model_path}")
        config = self._read_config()
        config = RuntimeConfig(
            model=ModelConfig(
                path=str(path),
                n_ctx=config.model.n_ctx,
                n_batch=config.model.n_batch,
                n_ubatch=config.model.n_ubatch,
            ),
            hardware=config.hardware,
            inference=config.inference,
        )
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        save_config(self._config_path, config)
        with self._runner_lock:
            runner = self._runner
            self._runner = None
        if runner is not None:
            unload = getattr(runner, "unload", None)
            if callable(unload):
                unload(timeout_s=4.0)
        return {"model_path": str(path)}

    def _update_settings(self, params: dict[str, Any]) -> dict[str, Any]:
        config = self._read_config()
        model = config.model
        hardware = config.hardware
        inference = config.inference
        if "temperature" in params:
            inference = InferenceConfig(
                max_tokens=inference.max_tokens,
                temperature=float(params["temperature"]),
                top_p=inference.top_p,
                stop=inference.stop,
                repeat_penalty=inference.repeat_penalty,
                repeat_last_n=inference.repeat_last_n,
            )
        if "top_p" in params:
            inference = InferenceConfig(
                max_tokens=inference.max_tokens,
                temperature=inference.temperature,
                top_p=float(params["top_p"]),
                stop=inference.stop,
                repeat_penalty=inference.repeat_penalty,
                repeat_last_n=inference.repeat_last_n,
            )
        if "max_tokens" in params:
            inference = InferenceConfig(
                max_tokens=max(64, min(8192, int(params["max_tokens"]))),
                temperature=inference.temperature,
                top_p=inference.top_p,
                stop=inference.stop,
                repeat_penalty=inference.repeat_penalty,
                repeat_last_n=inference.repeat_last_n,
            )
        if "n_ctx" in params:
            model = ModelConfig(
                path=model.path,
                n_ctx=max(2048, min(131072, int(params["n_ctx"]))),
                n_batch=model.n_batch,
                n_ubatch=model.n_ubatch,
            )
        if "n_batch" in params:
            model = ModelConfig(
                path=model.path,
                n_ctx=model.n_ctx,
                n_batch=max(64, min(8192, int(params["n_batch"]))),
                n_ubatch=model.n_ubatch,
            )
        if "n_gpu_layers" in params:
            hardware = HardwareConfig(
                n_gpu_layers=int(params["n_gpu_layers"]),
                n_threads=hardware.n_threads,
            )
        if "n_threads" in params:
            hardware = HardwareConfig(
                n_gpu_layers=hardware.n_gpu_layers,
                n_threads=max(0, int(params["n_threads"])),
            )
        updated = RuntimeConfig(model=model, hardware=hardware, inference=inference)
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        save_config(self._config_path, updated)
        reload_model = bool(params.get("reload_model"))
        if reload_model:
            with self._runner_lock:
                runner = self._runner
                self._runner = None
            if runner is not None:
                unload = getattr(runner, "unload", None)
                if callable(unload):
                    unload(timeout_s=4.0)
        return self._get_settings()

    def _fallback_title(self, goal: str) -> str:
        line = " ".join(goal.split()).strip()
        if len(line) <= 42:
            return line or "New agent"
        return f"{line[:41]}…"

    def _generate_title_request(self, params: dict[str, Any]) -> dict[str, Any]:
        goal = str(params.get("goal") or "")
        if not goal.strip():
            raise ServeError("goal is empty")
        # A title must never contend with the active coding request for the one
        # llama.cpp context.  The old implementation generated 24 model tokens
        # synchronously here, delaying every new GUI request by a full prefill.
        return {"title": self._fallback_title(goal)}

    def _start_run(self, params: dict[str, Any]) -> dict[str, Any]:
        with self._agent_lock:
            if self._busy:
                raise ServeError("agent is busy")
            self._busy = True
        self._session_id = str(params.get("session_id") or "")
        workspace = resolve_run_workspace(str(params.get("workspace") or ""), self._session_id)
        goal = str(params.get("goal") or "")
        thinking_level = str(params.get("thinking_level") or "off")
        thought_raw = params.get("thought_max_tokens")
        thought_max_tokens: int | None = None
        if thought_raw is not None and str(thought_raw).strip() != "":
            try:
                thought_max_tokens = max(32, min(4096, int(thought_raw)))
            except (TypeError, ValueError):
                thought_max_tokens = None
        mode = str(params.get("mode") or "")
        if not goal.strip():
            self._busy = False
            raise ServeError("goal is empty")
        if bool(params.get("generate_title")):
            # Keep request acknowledgement and model execution independent.
            # A deterministic title is instant and avoids a second, serial model
            # completion before the agent thread has even started.
            title = self._fallback_title(goal)
            mode_prefix = {
                "plan": "[Plan]",
                "ask": "[Ask]",
                "debug": "[Debug]",
                "refactor": "[Refactor]",
            }.get(mode, "")
            if mode_prefix and not title.startswith(mode_prefix):
                title = f"{mode_prefix} {title}"
            self.emit("agent.title", {"title": title})
        thread = threading.Thread(
            target=self._run,
            args=(str(workspace), goal, thinking_level, thought_max_tokens, mode),
            daemon=True,
            name="agent-run",
        )
        self._run_thread = thread
        thread.start()
        return {"status": "started", "session_id": self._session_id, "workspace": str(workspace)}

    def _run(
        self,
        workspace: str,
        goal: str,
        thinking_level: str = "off",
        thought_max_tokens: int | None = None,
        mode: str = "",
    ) -> None:
        try:
            if self._runner is None:
                self._load_model()
            preset = thinking_preset(thinking_level)
            effective_thought = (
                thought_max_tokens if thought_max_tokens is not None else preset.thought_max_tokens
            )
            print(
                f"[mango] agent loop workspace={workspace} thinking={preset.level} "
                f"thought_max_tokens={effective_thought} mode={mode or 'code'}",
                file=sys.stderr,
                flush=True,
            )
            from mango_agent.prompt import load_system_prompt

            if mode == "plan":
                orch = Orchestrator(
                    self._runner,
                    workspace=workspace,
                    limits=AgentLimits(
                        max_iterations=12,
                        max_runtime_seconds=600,
                        max_prompt_chars=24_000,
                        max_reasoning_cycles=preset.max_reasoning_cycles,
                        max_epistemic_iterations=8,
                    ),
                    max_tokens=4096,
                    on_event=self._on_agent_event,
                    system_prompt=load_system_prompt("plan"),
                    require_tools=True,
                    plan_mode=True,
                    plan_apis_first=False,
                    task_wants_tests=False,
                    disabled_tools=frozenset({"declare_apis"}),
                    thought_max_tokens=effective_thought,
                    tool_max_tokens=3072,
                    thinking_level=preset.level,
                    agent_mode="plan",
                )
            elif mode == "ask":
                orch = Orchestrator(
                    self._runner,
                    workspace=workspace,
                    limits=AgentLimits(
                        max_iterations=14,
                        max_runtime_seconds=600,
                        max_prompt_chars=24_000,
                        max_reasoning_cycles=preset.max_reasoning_cycles,
                        max_epistemic_iterations=8,
                    ),
                    max_tokens=4096,
                    on_event=self._on_agent_event,
                    system_prompt=load_system_prompt("ask"),
                    require_tools=True,
                    plan_mode=True,
                    plan_apis_first=False,
                    task_wants_tests=False,
                    disabled_tools=frozenset(
                        {
                            "declare_apis",
                            "codebase_lookup",
                            "ask_epistemic",
                            "research_codebase",
                            "package_source_lookup",
                            "doc_lookup",
                            "web_research",
                        }
                    ),
                    thought_max_tokens=effective_thought,
                    tool_max_tokens=3072,
                    thinking_level=preset.level,
                    agent_mode="ask",
                )
            elif mode == "refactor":
                orch = Orchestrator(
                    self._runner,
                    workspace=workspace,
                    limits=AgentLimits(
                        max_iterations=16,
                        max_runtime_seconds=600,
                        max_prompt_chars=24_000,
                        max_reasoning_cycles=preset.max_reasoning_cycles,
                        max_epistemic_iterations=6,
                    ),
                    max_tokens=4096,
                    on_event=self._on_agent_event,
                    system_prompt=load_system_prompt("refactor"),
                    require_tools=True,
                    plan_apis_first=False,
                    task_wants_tests=False,
                    disabled_tools=frozenset(
                        {"write_file", "delete_file", "run_terminal_command", "measure"}
                    ),
                    thought_max_tokens=effective_thought,
                    tool_max_tokens=3072,
                    thinking_level=preset.level,
                    agent_mode="refactor",
                )
            elif mode == "debug":
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
                    system_prompt=load_system_prompt("debug"),
                    require_tools=True,
                    plan_apis_first=True,
                    task_wants_tests=True,
                    thought_max_tokens=effective_thought,
                    tool_max_tokens=3072,
                    thinking_level=preset.level,
                    agent_mode="debug",
                )
            else:
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
                    # None = detect from goal. Forcing True made every Q&A run try pytest.
                    task_wants_tests=None,
                    thought_max_tokens=effective_thought,
                    tool_max_tokens=3072,
                    thinking_level=preset.level,
                    agent_mode="agent",
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
            # Remember the last checkpoint per session so undo_last_mutation still
            # works after the run thread finished and _current_agent is None.
            session = self._session_id or "default"
            agent = self._current_agent
            consumed = self._undo_history.setdefault(session, set())
            if agent is not None and getattr(agent, "_last_checkpoint_id", ""):
                self._undo_workspace[session] = str(getattr(agent, "_checkpoint_workspace", ""))
                # Mark everything except the newest checkpoint as consumed so the
                # first post-run undo reverts exactly that newest mutation.
                from mango_agent.checkpoints import _checkpoint_entries

                for path, _key in _checkpoint_entries(getattr(agent, "_run_id", "") or "default"):
                    if path.name != agent._last_checkpoint_id:
                        consumed.add(path.name)
            self._current_agent = None
            self._run_thread = None
            # Free VRAM after every prompt (finish or cancel). Keeping a large GGUF
            # resident between turns has been crashing Windows hosts; reload on
            # the next run is cheaper than an OS-level GPU hang.
            try:
                print(
                    "[mango] run ended — unloading model to free VRAM",
                    file=sys.stderr,
                    flush=True,
                )
                self._unload_runner(timeout_s=4.0)
                self.emit("model.unloaded", {})
            except Exception as unload_exc:  # noqa: BLE001
                print(
                    f"[mango] unload after run failed: {unload_exc}",
                    file=sys.stderr,
                    flush=True,
                )
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
        # If the run is stuck inside CUDA decode, finally never runs and VRAM stays
        # pinned — that has been crashing Windows. After a short grace period, drop
        # the llama handle without waiting for a CUDA free (same strategy as exit).
        threading.Thread(
            target=self._cancel_unload_watchdog,
            name="mango-cancel-unload",
            daemon=True,
        ).start()
        return {"status": "cancelling"}

    def _cancel_unload_watchdog(self) -> None:
        self._join_run(12.0)
        if not self._busy:
            return
        print(
            "[mango] cancel watchdog — run still busy; abandoning model handle",
            file=sys.stderr,
            flush=True,
        )
        with self._runner_lock:
            runner = self._runner
            self._runner = None
        if runner is None:
            return
        llama = getattr(runner, "_llama", None)
        if llama is not None:
            try:
                llama._closed = True
                llama.close = lambda *args, **kwargs: None  # type: ignore[method-assign]
            except Exception:
                pass
            try:
                runner._llama = None
            except Exception:
                pass
        try:
            self.emit("model.unloaded", {"forced": True})
        except Exception:
            pass

    def _continue_stall(self) -> dict[str, Any]:
        agent = self._current_agent
        if agent is None:
            return {"status": "idle", "continued": False}
        continue_fn = getattr(agent, "continue_after_stall", None)
        if callable(continue_fn):
            continue_fn()
            return {"status": "continued", "continued": True}
        clear = getattr(agent, "_clear_stall", None)
        if callable(clear):
            clear()
        if hasattr(agent, "_user_continue_stall"):
            agent._user_continue_stall = True
        return {"status": "continued", "continued": True}

    def _undo_last_mutation(self) -> dict[str, Any]:
        agent = self._current_agent
        session = self._session_id or "default"
        if agent is not None:
            undo = getattr(agent, "undo_last_mutation", None)
            if callable(undo):
                result = undo()
                if result.get("ok"):
                    self._mark_undone(session, str(result.get("checkpoint_id") or ""))
                return result
        # Run already finished: fall back to the persisted per-session history.
        from mango_agent import checkpoints as ck

        consumed = self._undo_history.setdefault(session, set())
        workspace = self._undo_workspace.get(session) or None
        result = ck.undo_last_mutation(
            session_id=self._last_checkpoint_session(), workspace=workspace, consumed=consumed
        )
        return result

    def _mark_undone(self, session: str, checkpoint_id: str) -> None:
        if checkpoint_id:
            self._undo_history.setdefault(session, set()).add(checkpoint_id)

    @staticmethod
    def _last_checkpoint_session() -> str:
        """The run id doubles as the checkpoints subfolder; use the newest one."""
        try:
            root = ck.checkpoints_root()
            candidates = [p for p in root.iterdir() if p.is_dir() and any(p.iterdir())]
        except OSError:
            return "default"
        if not candidates:
            return "default"
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
        return newest.name

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
        with self._runner_lock:
            runner = self._runner
            self._runner = None
        if runner is None:
            return
        unload = getattr(runner, "unload", None)
        if callable(unload):
            unload(timeout_s=timeout_s)

    def exit_process(self) -> None:
        """Cancel the run, neutralize CUDA, and exit as cleanly as possible.

        A hard process kill while the GPU is actively decoding can crash the
        Windows NVIDIA driver. We therefore cancel the agent loop, skip the
        blocking llama.cpp destructor, and let the OS reclaim VRAM safely.
        """
        self._cancel()
        self._join_run(2.0)

        # Skip the CUDA teardown that deadlocks on Windows. The OS will reclaim
        # the GPU memory once the process exits.
        with self._runner_lock:
            runner = self._runner
            self._runner = None
        if runner is not None:
            llama = getattr(runner, "_llama", None)
            if llama is not None:
                try:
                    llama._closed = True
                    llama.close = lambda *args, **kwargs: None
                except Exception:
                    pass

        try:
            sys.stdout.flush()
        except Exception:
            pass

        # Exit immediately. Python cleanup (including the non-daemon threads
        # created by the request pool) can hang; the OS reclaims the GPU context.
        os._exit(0)


def serve_loop(server: AgentServer, inp: TextIO, out: TextIO) -> None:
    # Process each JSONL request in a thread pool so a slow handler (e.g.
    # load_model) cannot block the read loop from handling health/cancel.
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=2, thread_name_prefix="mango-serve-"
    )
    shutdown_requested = threading.Event()

    def _dispatch(message: dict[str, Any]) -> None:
        ident = message.get("id")
        try:
            result = server.handle(message)
            server._write({"id": ident, "ok": True, "result": result})
        except ServeError as exc:
            server._write({"id": ident, "ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            server._write({"id": ident, "ok": False, "error": str(exc)})
        if message.get("method") == "shutdown":
            shutdown_requested.set()

    try:
        for raw in inp:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                server._write({"id": None, "ok": False, "error": f"invalid json: {exc}"})
                continue
            executor.submit(_dispatch, message)
            if shutdown_requested.is_set():
                break
    finally:
        # Do not wait for a slow handler (e.g. a stuck model load) to finish.
        # Cancel pending work and let exit_process terminate the process.
        executor.shutdown(wait=False, cancel_futures=True)
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
