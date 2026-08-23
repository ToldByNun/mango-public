"""Live AgentBridge wordstats — real model; require green pytest, no thrash."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from mango_cli.agent_bridge import AgentBridge

GOAL = (
    "Create a Python CLI tool called wordstats.py that analyzes a text file and "
    "prints word-frequency statistics. Requirements:\n"
    "Takes a file path as a command-line argument\n"
    "Counts word frequency (case-insensitive, ignore punctuation)\n"
    "Prints the top 10 most common words with their counts\n"
    "Handles the file-not-found case gracefully with a clear error message\n"
    "Include unit tests covering: normal input, empty file, and file-not-found\n"
    "Use only the Python standard library"
)


def main() -> int:
    ws = Path(tempfile.mkdtemp(prefix="wordstats_live_"))
    cfg = Path(r"C:\Users\mikaj\Desktop\DevDeck\runtime\config.yaml")
    print("workspace", ws, flush=True)

    run_tests = 0
    tools: list[str] = []

    def on_event(ev: dict) -> None:
        nonlocal run_tests
        blob = json.dumps(ev, default=str)
        et = str(ev.get("type") or "")
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        name = str(data.get("name") or data.get("tool") or "")
        if not name and "run_tests" in blob and et.endswith("tool"):
            name = "run_tests"
        if name:
            tools.append(name)
            if name == "run_tests":
                run_tests += 1
                print(f"TOOL run_tests #{run_tests}", flush=True)
            else:
                print(f"TOOL {name}", flush=True)

    bridge = AgentBridge(config_path=cfg, workspace=ws, session_id="wordstats-live7")
    bridge.attach_event_handler(on_event)
    print("loading...", flush=True)
    bridge.load()
    print("model", bridge.model_path, flush=True)

    t0 = time.time()
    result = bridge.run(GOAL, mode="")
    elapsed = time.time() - t0

    stop = getattr(result, "stop_reason", None)
    err = getattr(result, "error", None)
    print("STOP", stop, flush=True)
    print("ERROR", err, flush=True)
    print("ELAPSED_S", round(elapsed, 1), flush=True)
    print("RUN_TESTS_COUNT", run_tests, flush=True)
    print("TOOL_COUNTS", dict(Counter(tools)), flush=True)
    py = sorted(p.name for p in ws.rglob("*.py") if p.is_file())
    print("PY_FILES", py, flush=True)
    has_test = any(n.startswith("test_") or n.endswith("_test.py") for n in py)
    print("HAS_TEST", has_test, flush=True)

    if run_tests > 5:
        print("FAIL thrash run_tests", run_tests, flush=True)
        return 2
    if tools.count("write_file") > 12 and run_tests == 0:
        print("FAIL write-only thrash", flush=True)
        return 3
    if tools.count("edit_file") > 12 and run_tests == 0:
        print("FAIL edit-only thrash", flush=True)
        return 4
    if err and "never passed" in str(err).lower() and run_tests == 0:
        print("FAIL never ran tests but claimed tests failed", flush=True)
        return 5
    if not has_test:
        print("FAIL no test file kept", flush=True)
        return 6

    # Real proof: pytest must collect and pass on the workspace the agent left.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=line", str(ws)],
        cwd=ws,
        capture_output=True,
        text=True,
        timeout=60,
    )
    print("PYTEST_EXIT", proc.returncode, flush=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    if out:
        print("PYTEST_OUT", out[-400:], flush=True)
    if proc.returncode != 0:
        print("FAIL pytest not green on agent workspace", flush=True)
        return 7

    print("OK_GREEN", flush=True)
    return 0 if not err else 1


if __name__ == "__main__":
    raise SystemExit(main())
