"""Verify UI path does not hang when workspace is the Mango repo root."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("GGML_CUDA_DISABLE_GRAPHS", "1")
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "agent" / "python"))


def main() -> int:
    from mango_agent.agent_context import AgentLimits
    from mango_agent.orchestrator import Orchestrator
    from mango_runtime import ModelRunner

    runner = ModelRunner(str(REPO / "runtime" / "config.yaml"))
    runner.load()
    first: list[float] = []

    def on_event(message: dict) -> None:
        if message.get("event") == "agent.token" and message.get("payload", {}).get("delta"):
            if not first:
                first.append(time.monotonic())

    orch = Orchestrator(
        runner,
        workspace=REPO,
        limits=AgentLimits(max_iterations=2, max_runtime_seconds=60, max_prompt_chars=12_000),
        max_tokens=256,
        thought_max_tokens=96,
        on_event=on_event,
        require_tools=True,
    )
    t0 = time.monotonic()
    orch.run("Erstelle math_utils.py mit clamp(val, min_val, max_val).")
    elapsed = time.monotonic() - t0
    runner.unload()
    print(f"[repo-ui] elapsed={elapsed:.1f}s first_token={first[0]-t0:.1f}s" if first else f"[repo-ui] elapsed={elapsed:.1f}s NO TOKEN", flush=True)
    return 0 if first and first[0] - t0 < 30 else 1


if __name__ == "__main__":
    raise SystemExit(main())
