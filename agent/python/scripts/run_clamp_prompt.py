"""Run the UI clamp prompt against the real local model."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("GGML_CUDA_DISABLE_GRAPHS", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

PROMPT = (
    "Erstelle eine Datei math_utils.py mit einer Funktion clamp(val, min_val, max_val). "
    "Schreibe direkt einen passenden test_math_utils.py mit Pytest dazu und führe die Tests aus."
)

REPO = Path(__file__).resolve().parents[3]


def main() -> int:
    from mango_agent.agent_context import AgentLimits
    from mango_agent.orchestrator import Orchestrator
    from mango_runtime import ModelRunner

    workspace = Path(tempfile.mkdtemp(prefix="mango-clamp-"))
    print(f"[clamp] workspace={workspace}", flush=True)
    events: list[str] = []

    def on_event(message: dict) -> None:
        name = str(message.get("event") or "")
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        events.append(name)
        extra = ""
        if name == "agent.token" and payload.get("delta"):
            extra = repr(str(payload.get("delta"))[:80])
        elif name == "agent.file":
            extra = f"{payload.get('action')} {payload.get('path')}"
        elif name == "agent.tool":
            extra = str(payload.get("title") or payload.get("name") or "")
        elif name in {"agent.final", "agent.error", "agent.thought"}:
            extra = str(payload.get("text") or "")[:120]
        print(f"[clamp] {name} {extra}".rstrip(), flush=True)

    config = REPO / "runtime" / "config.yaml"
    runner = ModelRunner(str(config))
    runner.load()
    orch = Orchestrator(
        runner,
        workspace=workspace,
        limits=AgentLimits(max_iterations=8, max_runtime_seconds=180, max_prompt_chars=24_000),
        max_tokens=1024,
        thought_max_tokens=192,
        on_event=on_event,
        require_tools=True,
    )
    t0 = time.monotonic()
    result = orch.run(PROMPT)
    elapsed = time.monotonic() - t0
    print(
        f"[clamp] stop={result.stop_reason.value} iters={result.iterations} "
        f"elapsed={elapsed:.1f}s error={result.error!r}",
        flush=True,
    )
    print(f"[clamp] files={sorted(p.name for p in workspace.iterdir() if p.is_file())}", flush=True)

    math_utils = workspace / "math_utils.py"
    test_file = workspace / "test_math_utils.py"
    if not math_utils.is_file():
        print("[clamp] FAIL missing math_utils.py", flush=True)
        runner.unload()
        return 2
    if not test_file.is_file():
        print("[clamp] FAIL missing test_math_utils.py", flush=True)
        print(math_utils.read_text(encoding="utf-8")[:500], flush=True)
        runner.unload()
        return 3
    print("--- math_utils.py ---", flush=True)
    print(math_utils.read_text(encoding="utf-8"), flush=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short", str(test_file)],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    print(proc.stdout or "", flush=True)
    print(proc.stderr or "", flush=True)
    runner.unload()
    if proc.returncode != 0:
        print("[clamp] FAIL pytest", flush=True)
        return 4
    if "agent.file" not in events:
        print("[clamp] FAIL no file events", flush=True)
        return 5
    print("[clamp] PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
