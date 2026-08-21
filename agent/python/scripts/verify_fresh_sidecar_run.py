"""Step-1 check: fresh sidecar subprocess + clamp task (same IPC path as Electron)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROMPT = (
    "Erstelle eine Datei math_utils.py mit einer Funktion clamp(val, min_val, max_val). "
    "Schreibe direkt einen passenden test_math_utils.py mit Pytest dazu und führe die Tests aus."
)


def main() -> int:
    os.environ.setdefault("GGML_CUDA_DISABLE_GRAPHS", "1")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    python = REPO / "agent" / "python" / ".venv" / "Scripts" / "python.exe"
    config = REPO / "runtime" / "config.yaml"
    workspace = Path(tempfile.mkdtemp(prefix="mango-step1-"))
    print(f"[step1] workspace={workspace}", flush=True)

    proc = subprocess.Popen(
        [str(python), "-u", "-m", "mango_agent.serve", "--config", str(config)],
        cwd=str(REPO),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    assert proc.stdin and proc.stdout

    def request(method: str, params: dict | None = None) -> dict:
        req_id = str(int(time.time() * 1000))
        proc.stdin.write(json.dumps({"id": req_id, "method": method, "params": params or {}}) + "\n")
        proc.stdin.flush()
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line.strip():
                if proc.poll() is not None:
                    break
                continue
            msg = json.loads(line)
            if msg.get("event"):
                event = str(msg["event"])
                payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
                if event == "agent.tool":
                    print(f"[event] tool title={payload.get('title')} ok={payload.get('ok')}", flush=True)
                    body = str(payload.get("body") or "")
                    if body:
                        print(f"[event] body={body[:300]}", flush=True)
                elif event in {"agent.file", "agent.error", "agent.stopped"}:
                    print(f"[event] {event} {payload}", flush=True)
                continue
            if str(msg.get("id")) == req_id:
                if msg.get("ok") is False:
                    raise RuntimeError(str(msg.get("error")))
                return msg.get("result") or {}
        raise TimeoutError(method)

    timeouts: list[str] = []
    try:
        health = request("health")
        print(f"[step1] fresh sidecar health={health}", flush=True)
        started = time.monotonic()
        result = request(
            "run",
            {
                "session_id": "step1-verify",
                "goal": PROMPT,
                "workspace": str(workspace),
            },
        )
        print(f"[step1] run started: {result}", flush=True)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line.strip():
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            msg = json.loads(line)
            if not msg.get("event"):
                continue
            event = str(msg["event"])
            payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
            if event == "agent.tool":
                body = str(payload.get("body") or "")
                title = str(payload.get("title") or "")
                ok = payload.get("ok")
                print(f"[event] tool title={title!r} ok={ok}", flush=True)
                if "timed out after" in body:
                    timeouts.append(body.strip().splitlines()[0])
            if event == "agent.stopped":
                print(f"[event] stopped reason={payload.get('reason')} error={payload.get('error')}", flush=True)
                break
        elapsed = time.monotonic() - started
        print(f"[step1] elapsed={elapsed:.1f}s", flush=True)
        print(f"[step1] files={sorted(p.name for p in workspace.iterdir() if p.is_file())}", flush=True)
        if timeouts:
            print(f"[step1] TIMEOUT_MESSAGES={timeouts}", flush=True)
            return 1
        print("[step1] PASS no timeout on fresh sidecar", flush=True)
        return 0
    finally:
        try:
            proc.stdin.write(json.dumps({"id": "bye", "method": "shutdown"}) + "\n")
            proc.stdin.flush()
        except OSError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        err = proc.stderr.read() if proc.stderr else ""
        if err.strip():
            print("[step1] sidecar stderr tail:", err.strip()[-2000:], flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
