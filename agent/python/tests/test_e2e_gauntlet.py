"""Hard real-model E2E gauntlet: five production-style tasks, no mocks.

Each test builds a fresh workspace and gives the agent (GGUF model via
llama.cpp) a goal that requires multi-step tool work. Assertions check real
filesystem outcomes, not model prose. Run with live progress:

    pytest tests/test_e2e_gauntlet.py -s -m smoke

Use -s (or --capture=no) so progress lines print while the model runs.
Model load alone can take 1–2 minutes with no other output.

These are slow (minutes each). They exist to find loop/prompt/tool defects the
unit fakes cannot see. One shared ModelRunner is loaded per module to keep
model load time out of per-test wall time.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import pytest

from mango_agent import AgentLimits, Orchestrator, StopReason, log_loop_metrics

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("MANGO_GAUNTLET", "1") != "1",
        reason="MANGO_GAUNTLET=0 disables the real-model gauntlet",
    ),
]

MODEL_PATH = os.environ.get(
    "MANGO_GGUF_MODEL_PATH",
    r"C:\Users\mikaj\.lmstudio\models\ToldByNun\mango-1.0-iq2-xs\mango-1.0-Q2_K_L.gguf",
)

_MODEL_MISSING = not Path(MODEL_PATH).is_file()


def _progress_print(label: str, message: str) -> None:
    print(f"[gauntlet:{label}] {message}", file=sys.stderr, flush=True)


def make_gauntlet_progress(label: str) -> Callable[[dict[str, Any]], None]:
    """Print agent events to stderr so pytest -s shows live progress."""
    started = time.monotonic()

    def on_event(message: dict[str, Any]) -> None:
        event = str(message.get("event") or "")
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        elapsed = time.monotonic() - started
        prefix = f"+{elapsed:6.1f}s"

        if event == "agent.started":
            goal = str(payload.get("goal") or "")[:80].replace("\n", " ")
            _progress_print(label, f"{prefix} START {goal}")
        elif event == "agent.tool":
            title = str(payload.get("title") or payload.get("name") or "tool")
            streaming = " …" if payload.get("streaming") else ""
            _progress_print(label, f"{prefix} TOOL {title}{streaming}")
        elif event == "agent.file":
            _progress_print(
                label,
                f"{prefix} FILE {payload.get('action')} {payload.get('path')}",
            )
        elif event == "agent.experiment":
            _progress_print(
                label,
                f"{prefix} EXPERIMENT {payload.get('decision')} ({payload.get('reason')})",
            )
        elif event == "agent.syntax":
            _progress_print(
                label,
                f"{prefix} SYNTAX {payload.get('path')}: {str(payload.get('message') or '')[:100]}",
            )
        elif event == "agent.error":
            _progress_print(label, f"{prefix} ERROR {str(payload.get('text') or '')[:200]}")
        elif event == "agent.stopped":
            _progress_print(
                label,
                f"{prefix} STOPPED reason={payload.get('reason')} err={payload.get('error') or ''}",
            )
        elif event == "agent.final":
            text = str(payload.get("text") or "")[:120].replace("\n", " ")
            if text:
                _progress_print(label, f"{prefix} FINAL {text}")

    return on_event


@pytest.fixture(scope="module")
def runner():
    if _MODEL_MISSING:
        pytest.skip(f"GGUF model not available: {MODEL_PATH}")
    from mango_runtime import ModelRunner

    print(f"\n[gauntlet] Loading model (can take 1–2 min):\n  {MODEL_PATH}", file=sys.stderr, flush=True)
    os.environ.setdefault("MANGO_GGUF_MODEL_PATH", MODEL_PATH)
    t0 = time.monotonic()
    model = ModelRunner()
    model.load()
    print(f"[gauntlet] Model loaded in {time.monotonic() - t0:.1f}s\n", file=sys.stderr, flush=True)
    yield model
    print("[gauntlet] Unloading model…", file=sys.stderr, flush=True)
    model.unload(timeout_s=4.0)
    print("[gauntlet] Model unloaded.", file=sys.stderr, flush=True)


def _orchestrator(
    ws: Path,
    *,
    max_iterations: int = 16,
    label: str = "run",
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> Orchestrator:
    limits = AgentLimits(
        max_iterations=max_iterations,
        max_runtime_seconds=900.0,
        max_prompt_chars=24_000,
        max_reasoning_cycles=30,
    )
    return Orchestrator(
        _RUNNER_HOLDER["runner"],
        workspace=ws,
        limits=limits,
        max_tokens=4096,
        require_tools=True,
        thought_max_tokens=256,
        tool_max_tokens=2048,
        thinking_level="off",
        on_event=on_event or make_gauntlet_progress(label),
        verbose=True,
    )


_RUNNER_HOLDER: dict = {}


@pytest.fixture()
def agent_for(runner):
    holder = {"runner": runner}
    _RUNNER_HOLDER.clear()
    _RUNNER_HOLDER.update(holder)

    def _make(ws: Path, *, label: str = "run") -> Orchestrator:
        return _orchestrator(ws, label=label)

    return _make


def _run_gauntlet(orch: Orchestrator, task: str, label: str):
    _progress_print(label, f"BEGIN workspace={getattr(orch, 'workspace', None)}")
    t0 = time.monotonic()
    result = None
    try:
        result = orch.run(task)
    finally:
        orch.close()
    assert result is not None
    elapsed = time.monotonic() - t0
    _progress_print(
        label,
        f"DONE in {elapsed:.1f}s iterations={result.iterations} stop={result.stop_reason.value}",
    )
    log_loop_metrics(result, label)
    return result


@pytest.fixture()
def workspace():
    with tempfile.TemporaryDirectory(prefix="mango-gauntlet-") as tmp:
        yield Path(tmp)


def test_gauntlet_1_multi_file_rename(agent_for, workspace) -> None:
    """Cross-file API rename: rename class, update importers, keep tests green."""
    (workspace / "shapes.py").write_text(
        "class Circle:\n"
        "    def __init__(self, radius):\n"
        "        self.radius = radius\n\n"
        "    def area(self):\n"
        "        return 3 * self.radius ** 2\n",
        encoding="utf-8",
    )
    (workspace / "main.py").write_text(
        "from shapes import Circle\n\n\n"
        "def describe(radius):\n"
        "    c = Circle(radius)\n"
        '    return f"circle area={c.area()}"\n',
        encoding="utf-8",
    )
    (workspace / "test_shapes.py").write_text(
        "from shapes import Circle\n\n\n"
        "def test_area():\n"
        "    assert Circle(1).area() == 3\n",
        encoding="utf-8",
    )
    orch = agent_for(workspace)
    result = _run_gauntlet(
        orch,
        'Rename the class "Circle" to "Disk" in shapes.py and update main.py and '
        "test_shapes.py so everything still works.",
        "gauntlet_1_rename",
    )
    text = "\n".join(p.read_text(encoding="utf-8") for p in workspace.glob("*.py"))
    assert "class Disk" in text, f"rename did not happen:\n{text}"
    assert "class Circle" not in text, f"old class name still present:\n{text}"
    assert "Disk(" in text or "import Disk" in text, f"callers were not updated:\n{text}"
    assert result.stop_reason == StopReason.COMPLETED


def test_gauntlet_2_fix_failing_tests(agent_for, workspace) -> None:
    """Given failing impl + tests, fix code until pytest is green."""
    (workspace / "cart.py").write_text(
        "class Cart:\n"
        "    def __init__(self):\n"
        "        self.items = []\n\n"
        "    def add(self, name, price):\n"
        "        self.items.append((name, price))\n\n"
        "    def total(self):\n"
        "        s = 0\n"
        "        for name, price in self.items:\n"
        "            s += price\n"
        "        return int(s)  # BUG: truncates cents\n",
        encoding="utf-8",
    )
    (workspace / "test_cart.py").write_text(
        "import cart\n\n\n"
        "def test_total_cents():\n"
        "    c = cart.Cart()\n"
        "    c.add('apple', 0.5)\n"
        "    c.add('bread', 2.25)\n"
        "    assert c.total() == 2.75\n\n\n"
        "def test_empty_cart():\n"
        "    assert cart.Cart().total() == 0\n",
        encoding="utf-8",
    )
    orch = agent_for(workspace)
    result = _run_gauntlet(
        orch,
        "Run the tests in this workspace. Fix cart.py until every test passes "
        "(the total must keep cents, e.g. 2.75 stays 2.75). Do not modify tests.",
        "gauntlet_2_fix_tests",
    )
    content = (workspace / "cart.py").read_text(encoding="utf-8")
    assert "int(s)" not in content, f"buggy cast still present:\n{content}"
    assert result.stop_reason == StopReason.COMPLETED


def test_gauntlet_3_build_new_module_with_tests(agent_for, workspace) -> None:
    """Create a new module from a spec AND its own tests, all passing."""
    (workspace / "README.md").write_text("# Demo project\n", encoding="utf-8")
    orch = agent_for(workspace)
    result = _run_gauntlet(
        orch,
        "Create a module stack.py implementing a simple stack class Stack with "
        "push, pop, peek and is_empty methods (pop on empty raises IndexError). "
        "Also write test_stack.py with at least three tests and run them green.",
        "gauntlet_3_build_stack",
    )
    stack_py = workspace / "stack.py"
    test_py = workspace / "test_stack.py"
    assert stack_py.is_file(), "stack.py was not created"
    assert test_py.is_file(), "test_stack.py was not created"
    src = stack_py.read_text(encoding="utf-8")
    test_src = test_py.read_text(encoding="utf-8")
    assert "class Stack" in src, f"Stack class missing:\n{src}"
    assert "def test_" in test_src, f"test_stack.py has no test functions:\n{test_src}"
    assert result.stop_reason == StopReason.COMPLETED


def test_gauntlet_4_debug_crash_from_traceback(agent_for, workspace) -> None:
    """Entry script crashes at runtime; agent must diagnose via run and fix."""
    (workspace / "inventory.py").write_text(
        "ITEMS = {\n"
        '    "sword": {"price": 100, "qty": 3},\n'
        '    "shield": {"price": 80, "qty": 0},\n'
        "}\n",
        encoding="utf-8",
    )
    (workspace / "main.py").write_text(
        "import inventory\n\n\n"
        "def report():\n"
        "    lines = []\n"
        "    for name in inventory.ITEMS:\n"
        "        item = inventory.ITEMS[name]\n"
        "        value = item[\"price\"] * item[\"stock\"]\n"
        "        lines.append(f\"{name}: {value}\")\n"
        "    return \"\\n\".join(lines)\n\n\n"
        'if __name__ == "__main__":\n'
        "    print(report())\n",
        encoding="utf-8",
    )
    (workspace / "test_main.py").write_text(
        "from main import report\n\n\n"
        "def test_report_mentions_both():\n"
        '    out = report()\n'
        '    assert "sword" in out and "shield" in out\n',
        encoding="utf-8",
    )
    orch = agent_for(workspace)
    result = _run_gauntlet(
        orch,
        "Running main.py crashes. Find out why, fix it so main.py runs cleanly and "
        "the test passes. The value line must show price * quantity for each item.",
        "gauntlet_4_traceback_fix",
    )
    fixed = (workspace / "main.py").read_text(encoding="utf-8")
    assert '"stock"' not in fixed or '"qty"' in fixed.replace('"stock"', '"qty"')
    assert 'item["price"]' in fixed and ('item["qty"]' in fixed), (
        f"key mismatch not really fixed:\n{fixed}"
    )
    assert result.stop_reason == StopReason.COMPLETED


def test_gauntlet_5_multi_step_research_and_writeup(agent_for, workspace) -> None:
    """Read-only analysis across several files; answer must be written to disk."""
    (workspace / "sales_jan.csv").write_text(
        "month,item,amount\nJan,desk,3\nJan,lamp,10\n", encoding="utf-8",
    )
    (workspace / "sales_feb.csv").write_text(
        "month,item,amount\nFeb,desk,4\nFeb,lamp,6\n", encoding="utf-8",
    )
    (workspace / "prices.txt").write_text("desk=250\nlamp=40\n", encoding="utf-8")
    orch = agent_for(workspace)
    result = _run_gauntlet(
        orch,
        "Read sales_jan.csv, sales_feb.csv and prices.txt. Compute total revenue "
        "per item across both months and write the result as key=value lines into "
        "revenue_report.txt (e.g. desk=1750). Then summarize what you found.",
        "gauntlet_5_revenue",
    )
    report = workspace / "revenue_report.txt"
    assert report.is_file(), "revenue_report.txt was not created"
    body = report.read_text(encoding="utf-8")
    # desk: (3+4)*250 = 1750 ; lamp: (10+6)*40 = 640
    assert "1750" in body, f"desk revenue wrong:\n{body}"
    assert "640" in body, f"lamp revenue wrong:\n{body}"
    assert result.stop_reason == StopReason.COMPLETED


INVENTORY_CLI_GOAL = """\
schreib ein python projekt, das über die konsole läuft.
das projekt soll dafür da sein, bestehende items in meinem inventory zu tracken.
wir brauchen optionen um items hinzuzufügen, item count zu updaten, und items zu removen.
dazu auch item beschreibungen hinzufügen\
"""


def test_gauntlet_6_inventory_cli_greenfield(agent_for, workspace) -> None:
    """Greenfield CLI: must finish with a complete inventory.py, not a type-read loop."""
    from mango_agent.impl_completeness import find_impl_gaps

    _progress_print("inventory_cli", f"workspace={workspace}")
    orch = _orchestrator(workspace, max_iterations=24, label="inventory_cli")
    result = _run_gauntlet(orch, INVENTORY_CLI_GOAL, "inventory_cli")
    impl = workspace / "inventory.py"
    assert impl.is_file(), "inventory.py was not created"
    source = impl.read_text(encoding="utf-8")
    gaps = find_impl_gaps(source, INVENTORY_CLI_GOAL)
    assert not gaps, f"inventory.py still incomplete:\n" + "\n".join(gaps) + f"\n---\n{source}"
    assert 'if __name__ == "__main__"' in source
    type_attempts = sum(
        1
        for step in result.steps
        for call in step.tool_calls
        if call.name == "run_terminal_command"
        and "type" in str(call.arguments.get("command", "")).lower()
    )
    assert type_attempts == 0, "agent should use read_file, not type"
    assert result.stop_reason == StopReason.COMPLETED
