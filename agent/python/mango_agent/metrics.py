"""Run metrics for measure→build→measure (A0a).

Emits `agent.metrics` payloads, optional stderr JSON lines, and persists the last
N runs under ~/.mango/metrics/ for local baseline compare.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from mango_agent.flags import (
    RECOVERY_CORE_TOOLS,
    metrics_enabled,
    prompt_variant,
    resolve_tool_profile,
    tool_filter_mode,
    tool_profile,
)

DEFAULT_RETENTION = 50


@dataclass
class RunMetrics:
    """Serializable per-run observability payload."""

    run_id: str = ""
    scenario: str = ""
    stop_reason: str = ""
    iterations: int = 0
    tool_calls_total: int = 0
    tool_calls_by_name: dict[str, int] = field(default_factory=dict)
    edit_fail_count: int = 0
    write_fail_count: int = 0
    edit_attempts: int = 0
    write_attempts: int = 0
    edit_fail_rate: float = 0.0
    identical_tool_repeat_max: int = 0
    stall_triggered: bool = False
    stall_stopped: bool = False
    grammar_tool_count: int = 0
    grammar_missing_core_tools: list[str] = field(default_factory=list)
    grammar_filtered_tools: list[str] = field(default_factory=list)
    ttft_ms: float = 0.0
    total_prefill_s: float = 0.0
    total_decode_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    plan_gate_turns: int = 0
    epistemic_calls: int = 0
    prompt_variant: str = "v1"
    tool_filter_mode: str = "complete"
    tool_profile: str = "standard"
    reset_cache_used: int = 0
    elapsed_seconds: float = 0.0
    final_prompt_chars: int = 0
    verification_runs: int = 0
    verification_failures: int = 0
    ts: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def metrics_dir() -> Path:
    override = os.environ.get("MANGO_METRICS_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
    else:
        path = Path.home() / ".mango" / "metrics"
    path.mkdir(parents=True, exist_ok=True)
    return path


def compute_edit_fail_rate(fail_count: int, attempts: int) -> float:
    if attempts <= 0:
        return 0.0
    return round(fail_count / attempts, 4)


def missing_core_tools(grammar_names: list[str] | set[str], *, available: set[str] | None = None) -> list[str]:
    names = set(grammar_names)
    core = RECOVERY_CORE_TOOLS
    if available is not None:
        core = frozenset(t for t in core if t in available)
    return sorted(core - names)


def build_run_metrics(
    *,
    run_id: str = "",
    scenario: str = "",
    stop_reason: str = "",
    iterations: int = 0,
    tool_calls_by_name: dict[str, int] | None = None,
    edit_fail_count: int = 0,
    write_fail_count: int = 0,
    edit_attempts: int = 0,
    write_attempts: int = 0,
    identical_tool_repeat_max: int = 0,
    stall_triggered: bool = False,
    stall_stopped: bool = False,
    grammar_tool_names: list[str] | None = None,
    grammar_filtered_tools: list[str] | None = None,
    available_tools: set[str] | None = None,
    ttft_ms: float = 0.0,
    total_prefill_s: float = 0.0,
    total_decode_s: float = 0.0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    plan_gate_turns: int = 0,
    epistemic_calls: int = 0,
    reset_cache_used: int = 0,
    elapsed_seconds: float = 0.0,
    final_prompt_chars: int = 0,
    verification_runs: int = 0,
    verification_failures: int = 0,
    n_params: int | None = None,
) -> RunMetrics:
    by_name = dict(tool_calls_by_name or {})
    grammar_names = list(grammar_tool_names or [])
    profile = resolve_tool_profile(n_params=n_params)
    return RunMetrics(
        run_id=run_id,
        scenario=scenario,
        stop_reason=stop_reason,
        iterations=iterations,
        tool_calls_total=sum(by_name.values()),
        tool_calls_by_name=by_name,
        edit_fail_count=edit_fail_count,
        write_fail_count=write_fail_count,
        edit_attempts=edit_attempts,
        write_attempts=write_attempts,
        edit_fail_rate=compute_edit_fail_rate(edit_fail_count, edit_attempts),
        identical_tool_repeat_max=identical_tool_repeat_max,
        stall_triggered=stall_triggered,
        stall_stopped=stall_stopped,
        grammar_tool_count=len(grammar_names),
        grammar_missing_core_tools=missing_core_tools(grammar_names, available=available_tools),
        grammar_filtered_tools=list(grammar_filtered_tools or []),
        ttft_ms=round(ttft_ms, 3),
        total_prefill_s=round(total_prefill_s, 4),
        total_decode_s=round(total_decode_s, 4),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        plan_gate_turns=plan_gate_turns,
        epistemic_calls=epistemic_calls,
        prompt_variant=prompt_variant(),
        tool_filter_mode=tool_filter_mode(),
        tool_profile=profile if tool_profile() == "auto" else tool_profile(),
        reset_cache_used=reset_cache_used,
        elapsed_seconds=round(elapsed_seconds, 4),
        final_prompt_chars=final_prompt_chars,
        verification_runs=verification_runs,
        verification_failures=verification_failures,
    )


def emit_stderr_json(metrics: RunMetrics | dict[str, Any]) -> None:
    if not metrics_enabled():
        return
    payload = metrics.to_dict() if isinstance(metrics, RunMetrics) else dict(metrics)
    try:
        print(f"[mango.metrics] {json.dumps(payload, ensure_ascii=False)}", file=sys.stderr, flush=True)
    except Exception:
        return


def persist_run_metrics(metrics: RunMetrics | dict[str, Any], *, retention: int = DEFAULT_RETENTION) -> Path | None:
    if not metrics_enabled():
        return None
    payload = metrics.to_dict() if isinstance(metrics, RunMetrics) else dict(metrics)
    directory = metrics_dir()
    run_id = str(payload.get("run_id") or "run")
    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = directory / f"{stamp}_{run_id}.json"
    try:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        return None
    _prune_metrics(directory, retention=retention)
    return path


def _prune_metrics(directory: Path, *, retention: int) -> None:
    try:
        files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return
    for stale in files[max(1, retention) :]:
        try:
            stale.unlink()
        except Exception:
            pass


def compare_metrics(a: dict[str, Any], b: dict[str, Any], keys: list[str] | None = None) -> dict[str, Any]:
    """Delta table for baseline_pre vs baseline_post."""
    watch = keys or [
        "edit_fail_rate",
        "identical_tool_repeat_max",
        "stall_triggered",
        "stall_stopped",
        "grammar_missing_core_tools",
        "ttft_ms",
        "total_prefill_s",
        "iterations",
        "tool_calls_total",
    ]
    rows: dict[str, Any] = {}
    for key in watch:
        before = a.get(key)
        after = b.get(key)
        delta: Any = None
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            delta = after - before
        rows[key] = {"before": before, "after": after, "delta": delta}
    return rows


def load_metrics_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_baseline(path: str | Path, metrics: RunMetrics | dict[str, Any] | list[Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(metrics, RunMetrics):
        payload: Any = metrics.to_dict()
    else:
        payload = metrics
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target
