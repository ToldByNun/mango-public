"""Step 3b: full Orchestrator path + sidecar stderr pipe check (diagnostic only)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROMPT = (
    "Erstelle eine Datei math_utils.py mit einer Funktion clamp(val, min_val, max_val). "
    "Schreibe direkt einen passenden test_math_utils.py mit Pytest dazu und führe die Tests aus."
)


def _bootstrap() -> None:
    os.environ.setdefault("GGML_CUDA_DISABLE_GRAPHS", "1")
    sys.path[:0] = [
        str(REPO / "tools" / "python"),
        str(REPO / "runtime" / "python"),
        str(REPO / "agent" / "python"),
    ]


def orchestrator_run() -> dict[str, object]:
    from mango_agent.agent_context import AgentLimits
    from mango_agent.orchestrator import Orchestrator
    from mango_runtime import ModelRunner

    workspace = Path(tempfile.mkdtemp(prefix="mango-orch-repro-"))
    timeouts: list[str] = []
    events: list[str] = []

    def on_event(msg: dict) -> None:
        event = str(msg.get("event") or "")
        events.append(event)
        payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
        if event == "agent.tool":
            body = str(payload.get("body") or "")
            if "timed out" in body:
                timeouts.append(body.splitlines()[0])
            print(f"[orch] tool ok={payload.get('ok')} title={payload.get('title')}", flush=True)

    runner = ModelRunner(str(REPO / "runtime" / "config.yaml"))
    runner.load()
    orch = Orchestrator(
        runner,
        workspace=str(workspace),
        limits=AgentLimits(max_iterations=8, max_runtime_seconds=180, max_prompt_chars=24_000),
        max_tokens=1024,
        on_event=on_event,
        require_tools=True,
        thought_max_tokens=192,
    )
    t0 = time.perf_counter()
    result = orch.run(PROMPT)
    elapsed = round(time.perf_counter() - t0, 3)
    runner.unload()
    return {
        "case": "orchestrator_run_direct",
        "elapsed_s": elapsed,
        "stop_reason": result.stop_reason.value,
        "error": result.error,
        "timeouts": timeouts,
        "events": events,
        "files": sorted(p.name for p in workspace.iterdir() if p.is_file()),
    }


def serve_run(stderr_mode: str) -> dict[str, object]:
    python = REPO / "agent" / "python" / ".venv" / "Scripts" / "python.exe"
    workspace = Path(tempfile.mkdtemp(prefix="mango-serve-repro-"))
    config = REPO / "runtime" / "config.yaml"
    stderr_arg: int | None = subprocess.DEVNULL
    if stderr_mode == "pipe":
        stderr_arg = subprocess.PIPE
    elif stderr_mode == "thread_drain":
        stderr_arg = subprocess.PIPE

    proc = subprocess.Popen(
        [str(python), "-u", "-m", "mango_agent.serve", "--config", str(config)],
        cwd=str(REPO),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_arg,
        text=True,
        encoding="utf-8",
    )
    assert proc.stdin and proc.stdout
    drained: list[str] = []

    def drain_stderr() -> None:
        if proc.stderr is None:
            return
        for line in proc.stderr:
            drained.append(line.rstrip())

    if stderr_mode == "thread_drain":
        threading.Thread(target=drain_stderr, daemon=True).start()

    timeouts: list[str] = []

    def read_events_until_stopped() -> None:
        while True:
            line = proc.stdout.readline()
            if not line.strip():
                if proc.poll() is not None:
                    break
                continue
            msg = json.loads(line)
            if not msg.get("event"):
                continue
            event = str(msg["event"])
            payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
            if event == "agent.tool":
                body = str(payload.get("body") or "")
                if "timed out" in body:
                    timeouts.append(body.splitlines()[0])
            if event == "agent.stopped":
                break

    t0 = time.perf_counter()
    req_id = "1"
    proc.stdin.write(
        json.dumps(
            {
                "id": req_id,
                "method": "run",
                "params": {
                    "session_id": "serve-repro",
                    "goal": PROMPT,
                    "workspace": str(workspace),
                },
            }
        )
        + "\n"
    )
    proc.stdin.flush()
    read_events_until_stopped()
    elapsed = round(time.perf_counter() - t0, 3)
    try:
        proc.stdin.write(json.dumps({"id": "bye", "method": "shutdown"}) + "\n")
        proc.stdin.flush()
        proc.wait(timeout=15)
    except Exception:  # noqa: BLE001
        proc.kill()
    return {
        "case": f"serve_subprocess_stderr_{stderr_mode}",
        "elapsed_s": elapsed,
        "timeouts": timeouts,
        "stderr_lines": len(drained),
        "files": sorted(p.name for p in workspace.iterdir() if p.is_file()),
    }


def main() -> int:
    _bootstrap()
    results = [orchestrator_run()]
    for mode in ("devnull", "pipe", "thread_drain"):
        print(f"\n[3b] serve stderr mode={mode}", flush=True)
        results.append(serve_run(mode))
    print("\n[3b] SUMMARY", flush=True)
    print(json.dumps(results, indent=2), flush=True)
    bad = [r for r in results if r.get("timeouts")]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
