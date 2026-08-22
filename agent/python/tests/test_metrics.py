"""A0a: metrics shape, persistence, and agent.metrics emission."""

from __future__ import annotations

import json
import os
from pathlib import Path

from mango_agent import Agent, StopReason
from mango_agent.events import METRICS
from mango_agent.flags import RECOVERY_CORE_TOOLS, flag_snapshot, tool_filter_mode
from mango_agent.metrics import (
    build_run_metrics,
    compare_metrics,
    missing_core_tools,
    persist_run_metrics,
    write_baseline,
)
from test_agent_loop import FakeModelRunner


def test_missing_core_tools_lists_stripped_names() -> None:
    missing = missing_core_tools(["write_file", "edit_file"], available={"write_file", "edit_file", "read_file"})
    assert "read_file" in missing
    assert "write_file" not in missing


def test_build_run_metrics_shape(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MANGO_METRICS_DIR", str(tmp_path))
    monkeypatch.setenv("MANGO_METRICS", "1")
    metrics = build_run_metrics(
        run_id="abc",
        stop_reason="completed",
        iterations=3,
        tool_calls_by_name={"read_file": 1, "edit_file": 2},
        edit_fail_count=1,
        edit_attempts=2,
        grammar_tool_names=["write_file", "edit_file"],
        available_tools={"write_file", "edit_file", "read_file", "run_tests"},
        ttft_ms=12.5,
        reset_cache_used=1,
    )
    payload = metrics.to_dict()
    assert payload["edit_fail_rate"] == 0.5
    assert "read_file" in payload["grammar_missing_core_tools"]
    assert payload["tool_calls_total"] == 3
    assert payload["prompt_variant"]
    assert payload["tool_filter_mode"]
    path = persist_run_metrics(metrics)
    assert path is not None and path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["run_id"] == "abc"


def test_compare_metrics_delta() -> None:
    a = {"edit_fail_rate": 0.5, "identical_tool_repeat_max": 3, "ttft_ms": 100.0}
    b = {"edit_fail_rate": 0.2, "identical_tool_repeat_max": 1, "ttft_ms": 80.0}
    delta = compare_metrics(a, b)
    assert delta["edit_fail_rate"]["delta"] == -0.3
    assert delta["identical_tool_repeat_max"]["delta"] == -2


def test_agent_emits_metrics_event(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MANGO_METRICS_DIR", str(tmp_path / "metrics"))
    monkeypatch.setenv("MANGO_METRICS", "1")
    seen: list[dict] = []
    runner = FakeModelRunner(["Hello, no tools needed."])
    agent = Agent(runner, max_iterations=2, on_event=lambda event: seen.append(event))
    result = agent.run("Say hi.")
    assert result.stop_reason == StopReason.COMPLETED
    names = [item["event"] for item in seen]
    assert METRICS in names
    metrics_event = next(item for item in seen if item["event"] == METRICS)
    payload = metrics_event["payload"]
    assert "tool_calls_by_name" in payload
    assert "edit_fail_rate" in payload
    assert "grammar_missing_core_tools" in payload
    assert "ttft_ms" in payload
    assert payload["tool_filter_mode"] == tool_filter_mode()
    assert result.metrics.iterations >= 1


def test_flag_snapshot_keys() -> None:
    snap = flag_snapshot()
    assert "tool_filter_mode" in snap
    assert "metrics" in snap
    assert RECOVERY_CORE_TOOLS


def test_write_baseline(tmp_path: Path) -> None:
    metrics = build_run_metrics(run_id="baseline", iterations=1)
    path = write_baseline(tmp_path / "baseline_pre_A0.json", metrics)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["run_id"] == "baseline"
