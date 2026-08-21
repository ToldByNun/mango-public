"""Run the GUI Event Bus prompt against the local GGUF (same flags as serve.py)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("GGML_CUDA_DISABLE_GRAPHS", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

PROMPT = """Task:
Implement an in-memory, thread-safe Pub/Sub Event Bus in Python inside a file named event_bus.py. Then write a comprehensive test suite in test_event_bus.py using pytest.

Requirements:

Core Features:

subscribe(topic: str, handler: Callable[[Any], None]) -> str: Subscribes a handler to a topic and returns a unique subscription_id (UUID).

unsubscribe(subscription_id: str) -> bool: Unsubscribes the handler. Returns True if found and removed, False otherwise.

publish(topic: str, message: Any) -> int: Publishes a message to all handlers subscribed to the given topic. Handlers must be executed in parallel using a worker pool. Returns the number of handlers triggered.

Concurrency & Deadlock Prevention:

Topic subscriptions must be thread-safe (adding/removing subscribers concurrently while publishing should not throw RuntimeError: dictionary changed size during iteration).

Lock granularity must be fine-grained (e.g., publishing to topic A should not block subscriptions to topic B).

Fault Tolerance & Isolation:

If an individual handler raises an unhandled Exception during execution, it must NOT crash the publisher or prevent other handlers from receiving the message.

Errors must be caught and stored in an internal get_errors() ring-buffer (max 50 items).

Testing Requirements (test_event_bus.py):

Must include happy-path tests (subscribe, publish, unsubscribe).

Must include a high-concurrency stress test (concurrent.futures.ThreadPoolExecutor with at least 10 parallel threads constantly publishing, subscribing, and unsubscribing).

Must test subscriber error isolation (a failing subscriber doesn't stop others).
"""

REPO = Path(__file__).resolve().parents[3]


def main() -> int:
    from mango_agent.agent_context import AgentLimits
    from mango_agent.orchestrator import Orchestrator
    from mango_runtime import ModelRunner

    workspace = Path(tempfile.mkdtemp(prefix="mango-event-bus-"))
    print(f"[eventbus] workspace={workspace}", flush=True)
    tools: list[str] = []

    def on_event(message: dict) -> None:
        name = str(message.get("event") or "")
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        extra = ""
        if name == "agent.tool":
            title = str(payload.get("title") or payload.get("name") or "")
            tools.append(title)
            extra = title
        elif name == "agent.file":
            extra = f"{payload.get('action')} {payload.get('path')}"
        elif name in {"agent.final", "agent.error"}:
            extra = str(payload.get("text") or "")[:200]
        elif name == "agent.token" and payload.get("done"):
            extra = str(payload.get("text") or "")[:120]
        if extra or name in {"agent.started", "agent.stopped"}:
            print(f"[eventbus] {name} {extra}".rstrip(), flush=True)

    config = REPO / "runtime" / "config.yaml"
    runner = ModelRunner(str(config))
    runner.load()
    orch = Orchestrator(
        runner,
        workspace=workspace,
        limits=AgentLimits(
            max_iterations=20,
            max_runtime_seconds=900,
            max_prompt_chars=24_000,
            max_reasoning_cycles=0,
            max_epistemic_iterations=8,
        ),
        max_tokens=4096,
        thought_max_tokens=192,
        tool_max_tokens=2048,
        on_event=on_event,
        require_tools=True,
        plan_apis_first=True,
        task_wants_tests=True,
    )
    t0 = time.monotonic()
    result = orch.run(PROMPT)
    elapsed = time.monotonic() - t0
    print(
        f"[eventbus] stop={result.stop_reason.value} iters={result.iterations} "
        f"elapsed={elapsed:.1f}s error={result.error!r}",
        flush=True,
    )
    print(f"[eventbus] tools={tools}", flush=True)
    files = sorted(p.name for p in workspace.iterdir() if p.is_file())
    print(f"[eventbus] files={files}", flush=True)

    bus = workspace / "event_bus.py"
    test_file = workspace / "test_event_bus.py"
    if bus.is_file():
        print("--- event_bus.py ---", flush=True)
        print(bus.read_text(encoding="utf-8")[:4000], flush=True)
    if test_file.is_file():
        print("--- test_event_bus.py ---", flush=True)
        print(test_file.read_text(encoding="utf-8")[:4000], flush=True)

    failed = False
    if not bus.is_file():
        print("[eventbus] FAIL missing event_bus.py", flush=True)
        failed = True
    if not test_file.is_file():
        print("[eventbus] FAIL missing test_event_bus.py", flush=True)
        failed = True
    if tools.count("ask_epistemic") > 2 or sum(1 for item in tools if "epistemic" in item.lower()) > 2:
        print(f"[eventbus] FAIL too many epistemic calls: {tools}", flush=True)
        failed = True
    if not any("write" in item.lower() or item == "write_file" for item in tools) and not bus.is_file():
        print("[eventbus] FAIL no write_file", flush=True)
        failed = True

    code = 0
    if bus.is_file() and test_file.is_file():
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short", str(test_file)],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        print(proc.stdout or "", flush=True)
        print(proc.stderr or "", flush=True)
        if proc.returncode != 0:
            print("[eventbus] FAIL pytest", flush=True)
            failed = True
        else:
            print("[eventbus] pytest ok", flush=True)

    runner.unload()
    if failed:
        return 2
    print("[eventbus] PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
