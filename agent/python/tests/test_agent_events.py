from __future__ import annotations

from io import StringIO
from pathlib import Path

from mango_agent.events import line_stats, tool_title, unified_diff
from mango_agent.serve import AgentServer, is_mango_source_tree, resolve_run_workspace
from test_agent_loop import FakeModelRunner
from mango_agent import Agent, StopReason
from mango_tools import create_default_registry


def test_line_stats_counts_inserts_and_deletes() -> None:
    added, removed = line_stats("a\nb\n", "a\nc\nd\n")
    assert added == 2
    assert removed == 1


def test_unified_diff_contains_filenames() -> None:
    text = unified_diff("app/foo.py", "x = 1\n", "x = 2\n")
    assert "foo.py" in text
    assert "-x = 1" in text
    assert "+x = 2" in text


def test_tool_title_lookup() -> None:
    assert "clamp" in tool_title("codebase_lookup", {"symbol": "clamp"})
    assert "pandas" in tool_title("declare_apis", {"libraries": "pandas, argparse"})
    assert "epistemic" in tool_title("ask_epistemic", {"question": "pandas read_csv"})
    assert "Lock" in tool_title("package_source_lookup", {"package": "threading", "symbol": "Lock"})
    assert "timeit" in tool_title("measure", {"command": "python -m timeit"})


def test_agent_emits_file_event_on_write(tmp_path: Path) -> None:
    target = tmp_path / "note.txt"
    target.write_text("alpha\n", encoding="utf-8")
    seen: list[dict] = []
    import json

    call = f'<tool_call=write_file : {json.dumps({"path": str(target), "content": "beta\n"})}>'
    runner = FakeModelRunner([call, "updated the file"])
    agent = Agent(
        runner,
        max_iterations=3,
        on_event=lambda event: seen.append(event),
        tool_registry=create_default_registry(),
    )
    result = agent.run(f"Change {target} to beta")
    assert result.stop_reason == StopReason.COMPLETED
    names = [item["event"] for item in seen]
    assert "agent.started" in names
    assert "agent.file" in names
    assert "agent.stopped" in names
    file_event = next(item for item in seen if item["event"] == "agent.file")
    assert file_event["payload"]["added"] >= 1 or file_event["payload"]["removed"] >= 1


def test_serve_health_and_run_jsonl(tmp_path: Path) -> None:
    out = StringIO()
    server = AgentServer(None, out)
    server._runner = FakeModelRunner(["All done.", "All done.", "All done."])
    health = server.handle({"method": "health"})
    assert health["status"] == "ok"
    started = server.handle(
        {
            "method": "run",
            "params": {"session_id": "s1", "goal": "Say hi", "workspace": str(tmp_path)},
        }
    )
    assert started["status"] == "started"
    for _ in range(80):
        if not server._busy:
            break
        import time

        time.sleep(0.05)
    assert server._busy is False
    dumped = out.getvalue()
    assert "agent.started" in dumped
    assert "agent.stopped" in dumped


def test_resolve_run_workspace_rejects_mango_repo(tmp_path: Path) -> None:
    repo = tmp_path / "Mango"
    (repo / "runtime").mkdir(parents=True)
    (repo / "agent" / "python" / "mango_agent").mkdir(parents=True)
    (repo / "apps" / "electron").mkdir(parents=True)
    (repo / "runtime" / "config.yaml").write_text("model: {}\n", encoding="utf-8")
    assert is_mango_source_tree(repo)
    isolated = resolve_run_workspace(str(repo), "sess-1")
    assert isolated != repo.resolve()
    assert isolated.is_dir()
    safe = tmp_path / "project"
    safe.mkdir()
    assert resolve_run_workspace(str(safe), "sess-1") == safe.resolve()


def test_serve_run_tests_in_user_workspace(tmp_path: Path) -> None:
    import json
    import time

    impl = "def clamp(v, lo, hi):\n    return max(lo, min(hi, v))\n"
    test_body = "from math_utils import clamp\n\ndef test_clamp():\n    assert clamp(5, 0, 10) == 5\n"
    write_impl = json.dumps({"path": "math_utils.py", "content": impl})
    write_test = json.dumps({"path": "test_math_utils.py", "content": test_body})
    calls = [
        f"<tool_call=write_file : {write_impl}>",
        f"<tool_call=write_file : {write_test}>",
        "<tool_call=run_tests : {}>",
        "Done.",
    ]
    out = StringIO()
    server = AgentServer(None, out)
    server._runner = FakeModelRunner(calls)
    started = server.handle(
        {
            "method": "run",
            "params": {
                "session_id": "clamp-ui",
                "goal": "Create clamp and run pytest",
                "workspace": str(tmp_path),
            },
        }
    )
    assert started["workspace"] == str(tmp_path.resolve())
    for _ in range(200):
        if not server._busy:
            break
        time.sleep(0.05)
    assert server._busy is False
    dumped = out.getvalue()
    assert "agent.tool" in dumped
    assert (tmp_path / "math_utils.py").is_file()
    assert (tmp_path / "test_math_utils.py").is_file()
    assert '"ok": true' in dumped.lower() or "Tests failed" not in dumped


def test_agent_emits_token_events() -> None:
    seen: list[dict] = []
    runner = FakeModelRunner(["Hello from the model."])
    agent = Agent(
        runner,
        max_iterations=2,
        on_event=lambda event: seen.append(event),
        tool_registry=create_default_registry(),
    )
    result = agent.run("Say hi")
    assert result.stop_reason == StopReason.COMPLETED
    tokens = [item for item in seen if item["event"] == "agent.token"]
    assert tokens
    assert any(item["payload"].get("delta") == "Hello from the model." for item in tokens)
    assert any(item["payload"].get("done") is True for item in tokens)
