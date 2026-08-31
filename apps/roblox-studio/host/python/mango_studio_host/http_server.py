"""Stdlib HTTP server for the Studio plugin + internal sidecar tool bridge."""

from __future__ import annotations

import json
import threading
import time
import traceback
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from mango_studio_host.paths import find_repo_root, runtime_config_path, studio_workspace
from mango_studio_host.rojo import find_rojo_project, rojo_tree_root
from mango_studio_host.sidecar_client import SidecarClient
from mango_studio_host.studio_bridge import StudioBridge

DEFAULT_PORT = 17880
DEFAULT_HOST = "127.0.0.1"


class EventBus:
    """Ring buffer of agent events for plugin long-poll streaming."""

    def __init__(self, maxlen: int = 2000) -> None:
        self._lock = threading.Lock()
        self._events: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._seq = 0
        self._wake = threading.Condition(self._lock)

    def publish(self, event: dict[str, Any]) -> None:
        with self._wake:
            self._seq += 1
            payload = dict(event)
            payload["_seq"] = self._seq
            self._events.append(payload)
            self._wake.notify_all()

    def poll_since(self, since: int, *, wait_s: float = 25.0) -> list[dict[str, Any]]:
        deadline = time.time() + max(0.1, wait_s)
        with self._wake:
            while True:
                batch = [e for e in self._events if int(e.get("_seq") or 0) > since]
                if batch:
                    return batch
                remaining = deadline - time.time()
                if remaining <= 0:
                    return []
                self._wake.wait(timeout=remaining)


class HostState:
    def __init__(self, *, port: int = DEFAULT_PORT) -> None:
        self.port = port
        self.repo_root = find_repo_root()
        self.config_path = runtime_config_path(self.repo_root)
        self.bridge = StudioBridge()
        self.events = EventBus()
        self.sidecar: SidecarClient | None = None
        self.busy = False
        self.session_id = ""
        self.last_error = ""
        self.settings: dict[str, Any] = {
            "port": port,
            "confirm_prop_threshold": 1,
            "model_path": "",
            "thinking_level": "off",
        }
        self._lock = threading.Lock()

    def ensure_sidecar(self) -> SidecarClient:
        with self._lock:
            if self.sidecar and self.sidecar.running:
                return self.sidecar
            bridge_url = f"http://{DEFAULT_HOST}:{self.port}"
            client = SidecarClient(
                repo_root=self.repo_root,
                config_path=self.config_path,
                on_event=self._on_sidecar_event,
                extra_env={"MANGO_STUDIO_BRIDGE_URL": bridge_url},
            )
            client.start()
            self.sidecar = client
            return client

    def _on_sidecar_event(self, message: dict[str, Any]) -> None:
        self.events.publish(message)
        event = str(message.get("event") or "")
        if event in {"agent.stopped", "agent.error"}:
            self.busy = False
        if event == "agent.started":
            self.busy = True

    def health(self) -> dict[str, Any]:
        sidecar_ok = bool(self.sidecar and self.sidecar.running)
        model_loaded = False
        if sidecar_ok and self.sidecar:
            try:
                info = self.sidecar.request("health", {}, timeout_s=5.0)
                model_loaded = bool(info.get("model_loaded"))
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)
                sidecar_ok = False
        rojo = find_rojo_project(self.repo_root)
        return {
            "status": "ok",
            "host": "mango-studio-host",
            "version": "0.1.0",
            "sidecar": sidecar_ok,
            "model_loaded": model_loaded,
            "busy": self.busy,
            "pending_studio_calls": self.bridge.pending_count(),
            "port": self.port,
            "last_error": self.last_error,
            "rojo_project": str(rojo) if rojo else None,
            "transport": "long-poll",
        }


def _json_response(handler: BaseHTTPRequestHandler, status: int, body: Any) -> None:
    raw = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, x-api-key")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(raw)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def make_handler(state: HostState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            # Keep quiet; important lines go to stderr via print in callers.
            return

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, x-api-key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            qs = parse_qs(parsed.query)
            try:
                if path in {"/health", "/"}:
                    _json_response(self, 200, state.health())
                    return
                if path == "/v1/settings":
                    settings = dict(state.settings)
                    if state.sidecar and state.sidecar.running:
                        try:
                            remote = state.sidecar.request("get_settings", {}, timeout_s=10.0)
                            settings.update(remote)
                        except Exception as exc:  # noqa: BLE001
                            settings["sidecar_error"] = str(exc)
                    _json_response(self, 200, settings)
                    return
                if path == "/v1/events":
                    since = int((qs.get("since") or ["0"])[0] or 0)
                    wait_s = float((qs.get("wait") or ["25"])[0] or 25)
                    batch = state.events.poll_since(since, wait_s=wait_s)
                    _json_response(self, 200, {"events": batch, "since": since})
                    return
                if path == "/v1/studio/poll":
                    wait_s = float((qs.get("wait") or ["25"])[0] or 25)
                    call = state.bridge.poll(wait_s=wait_s)
                    if call is None:
                        _json_response(self, 200, {"request": None})
                    else:
                        _json_response(self, 200, {"request": call})
                    return
                _json_response(self, 404, {"error": "not_found", "path": path})
            except Exception as exc:  # noqa: BLE001
                _json_response(
                    self,
                    500,
                    {"error": str(exc), "traceback": traceback.format_exc()},
                )

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            body = _read_json(self)
            try:
                if path == "/internal/studio/call":
                    # Called by rbx_* tools inside the sidecar process.
                    tool = str(body.get("tool") or "")
                    args = body.get("args") if isinstance(body.get("args"), dict) else {}
                    requires_confirm = bool(body.get("requires_confirm"))
                    confirm_summary = str(body.get("confirm_summary") or "")
                    timeout_s = body.get("timeout_s")
                    result = state.bridge.call(
                        tool,
                        args,
                        requires_confirm=requires_confirm,
                        confirm_summary=confirm_summary,
                        timeout_s=float(timeout_s) if timeout_s is not None else None,
                    )
                    _json_response(self, 200, result)
                    return

                if path == "/v1/studio/result":
                    request_id = str(body.get("request_id") or "")
                    ok = state.bridge.complete(request_id, body)
                    _json_response(self, 200 if ok else 404, {"ok": ok})
                    return

                if path == "/v1/settings":
                    for key in ("confirm_prop_threshold", "thinking_level"):
                        if key in body:
                            state.settings[key] = body[key]
                    if "model_path" in body and str(body["model_path"]).strip():
                        state.ensure_sidecar().request(
                            "set_model_path",
                            {"path": str(body["model_path"])},
                            timeout_s=30.0,
                        )
                        state.settings["model_path"] = str(body["model_path"])
                    _json_response(self, 200, state.settings)
                    return

                if path == "/v1/run":
                    session_id = str(body.get("session_id") or "studio")
                    goal = str(body.get("goal") or "")
                    mode = str(body.get("mode") or "roblox")
                    thinking_level = str(
                        body.get("thinking_level") or state.settings.get("thinking_level") or "off"
                    )
                    selection = body.get("selection")
                    if selection:
                        goal = f"{goal}\n\n[Studio selection]\n{selection}".strip()
                    workspace = str(body.get("workspace") or "")
                    if not workspace:
                        rojo = find_rojo_project(state.repo_root)
                        if rojo:
                            root = rojo_tree_root(rojo)
                            workspace = str(root) if root else str(studio_workspace(session_id))
                        else:
                            workspace = str(studio_workspace(session_id))
                    state.session_id = session_id
                    state.busy = True
                    state.last_error = ""
                    sidecar = state.ensure_sidecar()
                    # Fire-and-forget: run returns immediately; events stream via /v1/events
                    result = sidecar.request(
                        "run",
                        {
                            "session_id": session_id,
                            "goal": goal,
                            "workspace": workspace,
                            "mode": mode,
                            "thinking_level": thinking_level,
                            "generate_title": True,
                        },
                        timeout_s=30.0,
                    )
                    _json_response(self, 200, {**result, "workspace": workspace})
                    return

                if path == "/v1/cancel":
                    if state.sidecar and state.sidecar.running:
                        result = state.sidecar.request("cancel", {}, timeout_s=10.0)
                        _json_response(self, 200, result)
                    else:
                        _json_response(self, 200, {"status": "idle"})
                    state.busy = False
                    return

                if path == "/v1/undo":
                    if state.sidecar and state.sidecar.running:
                        result = state.sidecar.request("undo_last_mutation", {}, timeout_s=30.0)
                        _json_response(self, 200, result)
                    else:
                        _json_response(self, 400, {"error": "sidecar_not_running"})
                    return

                if path == "/v1/load_model":
                    result = state.ensure_sidecar().request("load_model", {}, timeout_s=600.0)
                    _json_response(self, 200, result)
                    return

                _json_response(self, 404, {"error": "not_found", "path": path})
            except Exception as exc:  # noqa: BLE001
                state.last_error = str(exc)
                state.busy = False
                _json_response(
                    self,
                    500,
                    {"error": str(exc), "traceback": traceback.format_exc()},
                )

    return Handler


def serve_forever(*, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    state = HostState(port=port)
    handler = make_handler(state)
    server = ThreadingHTTPServer((host, port), handler)
    print(
        f"[mango-studio-host] listening on http://{host}:{port}  repo={state.repo_root}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[mango-studio-host] shutting down", flush=True)
    finally:
        if state.sidecar:
            try:
                state.sidecar.stop()
            except Exception:
                pass
        server.server_close()
