"""A4: A/B compare prompt v1 vs v2 against fake-runner golden scenarios.

Exit 0 when v2 does not regress tool-correctness / stall proxies vs v1.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for rel in (
    "agent/python",
    "tools/python",
    "context/python",
    "cot/python",
    "runtime/python",
    "verification/python",
    "codeintel/python",
    "epistemic/python",
    "agent/python/tests",
):
    path = REPO / rel
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from mango_agent import Agent  # noqa: E402
from mango_tools import create_default_registry  # noqa: E402
from test_agent_loop import FakeModelRunner  # noqa: E402


def _run(variant: str) -> dict:
    os.environ["MANGO_PROMPT_VARIANT"] = variant
    os.environ["MANGO_METRICS"] = "1"
    note_dir = Path(tempfile.mkdtemp(prefix=f"mango-ab-{variant}-"))
    note = note_dir / "note.txt"
    note.write_text("alpha\n", encoding="utf-8")
    read = f'<tool_call=read_file : {json.dumps({"path": str(note)})}>'
    edit = (
        f'<tool_call=edit_file : '
        f'{json.dumps({"path": str(note), "old_string": "alpha", "new_string": "beta"})}>'
    )
    runner = FakeModelRunner([f"Read.\n{read}", f"Edit.\n{edit}", "Done."])
    seen: list[dict] = []
    agent = Agent(
        runner,
        max_iterations=6,
        on_event=lambda e: seen.append(e),
        tool_registry=create_default_registry(),
        system_prompt=None,
    )
    # Force reload of variant via compose path used in Agent.__init__ when system_prompt is None —
    # Agent already composed at init; rebuild prompt by constructing with compose.
    from mango_agent.prompt import compose_agent_system_prompt

    agent = Agent(
        runner,
        max_iterations=6,
        on_event=lambda e: seen.append(e),
        tool_registry=create_default_registry(),
        system_prompt=compose_agent_system_prompt("off"),
    )
    result = agent.run("Read and edit note.txt from alpha to beta.")
    metrics = next((e["payload"] for e in seen if e.get("event") == "agent.metrics"), {})
    return {
        "variant": variant,
        "stop_reason": result.stop_reason.value,
        "edit_fail_rate": metrics.get("edit_fail_rate", 0),
        "stall_stopped": metrics.get("stall_stopped", False),
        "identical_tool_repeat_max": metrics.get("identical_tool_repeat_max", 0),
        "tool_calls_by_name": metrics.get("tool_calls_by_name", {}),
        "final_ok": note.read_text(encoding="utf-8") == "beta\n",
    }


def main() -> int:
    v1 = _run("v1")
    v2 = _run("v2")
    print(json.dumps({"v1": v1, "v2": v2}, indent=2))
    # Merge gate: v2 must not regress.
    ok = (
        v2["final_ok"]
        and v2["edit_fail_rate"] <= v1["edit_fail_rate"]
        and int(v2["identical_tool_repeat_max"]) <= int(v1["identical_tool_repeat_max"]) + 1
        and not v2["stall_stopped"]
    )
    out = REPO / "agent" / "baselines" / "prompt_ab_v1_v2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"v1": v1, "v2": v2, "merge_v2": ok}, indent=2) + "\n", encoding="utf-8")
    print(f"[ab] merge_v2={ok} wrote {out}", flush=True)
    if ok:
        # Promote default to v2 by documenting env; keep agent.md as v1 forever.
        print("[ab] v2 non-regressing — set MANGO_PROMPT_VARIANT=v2 as default when ready", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
