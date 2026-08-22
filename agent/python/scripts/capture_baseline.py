"""Capture fake-runner baseline metrics (A0a) without requiring a GPU model.

Usage:
  python -m scripts.capture_baseline --out agent/baselines/baseline_pre_A0.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
AGENT_PYTHON = REPO / "agent" / "python"
if str(AGENT_PYTHON) not in sys.path:
    sys.path.insert(0, str(AGENT_PYTHON))
TOOLS = REPO / "tools" / "python"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
CONTEXT = REPO / "context" / "python"
if str(CONTEXT) not in sys.path:
    sys.path.insert(0, str(CONTEXT))
COT = REPO / "cot" / "python"
if str(COT) not in sys.path:
    sys.path.insert(0, str(COT))
RUNTIME = REPO / "runtime" / "python"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))
VERIFICATION = REPO / "verification" / "python"
if str(VERIFICATION) not in sys.path:
    sys.path.insert(0, str(VERIFICATION))
CODEINTEL = REPO / "codeintel" / "python"
if str(CODEINTEL) not in sys.path:
    sys.path.insert(0, str(CODEINTEL))
EPISTEMIC = REPO / "epistemic" / "python"
if str(EPISTEMIC) not in sys.path:
    sys.path.insert(0, str(EPISTEMIC))

from mango_agent import Agent  # noqa: E402
from mango_agent.metrics import write_baseline  # noqa: E402
from mango_tools import create_default_registry  # noqa: E402

# Import FakeModelRunner from tests without pytest collection side effects.
sys.path.insert(0, str(AGENT_PYTHON / "tests"))
from test_agent_loop import FakeModelRunner  # noqa: E402


SCENARIOS = [
    {
        "name": "say_hi",
        "goal": "Say hi.",
        "outputs": ["Hello, no tools needed."],
    },
    {
        "name": "read_then_done",
        "goal": "Read note.txt then stop.",
        "outputs": None,  # filled after workspace setup
    },
    {
        "name": "edit_loop_proxy",
        "goal": "Edit note.txt from alpha to beta.",
        "outputs": None,
    },
]


def _run_scenario(tmp: Path, scenario: dict) -> dict:
    tmp.mkdir(parents=True, exist_ok=True)
    note = tmp / "note.txt"
    note.write_text("alpha\n", encoding="utf-8")
    name = scenario["name"]
    if name == "read_then_done":
        call = f'<tool_call=read_file : {json.dumps({"path": str(note)})}>'
        outputs = [f"Reading.\n{call}", "Done reading."]
    elif name == "edit_loop_proxy":
        bad = (
            f'<tool_call=edit_file : '
            f'{json.dumps({"path": str(note), "old_string": "alphx", "new_string": "beta"})}>'
        )
        good = (
            f'<tool_call=edit_file : '
            f'{json.dumps({"path": str(note), "old_string": "alpha", "new_string": "beta"})}>'
        )
        outputs = [f"Try edit.\n{bad}", f"Retry.\n{good}", "Edited."]
    else:
        outputs = list(scenario["outputs"] or ["ok"])

    seen: list[dict] = []
    runner = FakeModelRunner(outputs)
    agent = Agent(
        runner,
        max_iterations=6,
        on_event=lambda event: seen.append(event),
        tool_registry=create_default_registry(),
    )
    result = agent.run(scenario["goal"])
    metrics_events = [e for e in seen if e.get("event") == "agent.metrics"]
    payload = metrics_events[-1]["payload"] if metrics_events else result.to_dict().get("metrics", {})
    payload = dict(payload)
    payload["scenario"] = name
    payload["stop_reason"] = result.stop_reason.value
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture A0a baseline metrics (fake runner)")
    parser.add_argument(
        "--out",
        default=str(REPO / "agent" / "baselines" / "baseline_pre_A0.json"),
        help="Output JSON path",
    )
    args = parser.parse_args(argv)

    import tempfile

    runs: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="mango-baseline-") as raw:
        tmp = Path(raw)
        for scenario in SCENARIOS:
            for repeat in range(2):
                payload = _run_scenario(tmp / f"{scenario['name']}_{repeat}", scenario)
                payload["repeat"] = repeat
                runs.append(payload)
                print(
                    f"[baseline] {scenario['name']}#{repeat} "
                    f"edit_fail_rate={payload.get('edit_fail_rate')} "
                    f"missing_core={payload.get('grammar_missing_core_tools')}",
                    flush=True,
                )

    summary = {
        "kind": Path(args.out).stem,
        "runner": "fake",
        "runs": runs,
        "aggregates": {
            "edit_fail_rate_mean": sum(float(r.get("edit_fail_rate") or 0) for r in runs) / max(1, len(runs)),
            "identical_tool_repeat_max_mean": sum(
                int(r.get("identical_tool_repeat_max") or 0) for r in runs
            )
            / max(1, len(runs)),
            "stall_stopped_count": sum(1 for r in runs if r.get("stall_stopped")),
            "grammar_missing_core_any": any(r.get("grammar_missing_core_tools") for r in runs),
        },
        "latency_note": (
            "Fake runner TTFT is 0. Acceptance target after real-model smoke only."
        ),
    }
    path = write_baseline(args.out, summary)
    print(f"[baseline] wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
