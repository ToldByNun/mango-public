"""JSON and Markdown reports for a benchmark run."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_reports(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = dict(payload)
    payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    json_path = output_dir / f"benchmark-{stamp}.json"
    md_path = output_dir / f"benchmark-{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    return json_path, md_path


def render_markdown(payload: dict[str, Any]) -> str:
    tasks = list(payload.get("tasks") or [])
    lines = [
        "# Mango coding benchmark",
        "",
        f"- Created: {payload.get('created_at', '')}",
        f"- Tasks: {payload.get('passed', 0)}/{payload.get('task_count', 0)} passed "
        f"({float(payload.get('pass_rate') or 0) * 100:.1f}%)",
        f"- Total tokens: {payload.get('total_tokens', 0)}",
        f"- Total time: {payload.get('total_elapsed_seconds', 0)}s",
        f"- Tasks that used epistemic: {payload.get('used_epistemic_tasks', 0)}",
        f"- Tasks that used verification fix-loop: {payload.get('used_fix_loop_tasks', 0)}",
        "",
        "| Task | Cat | Diff | Result | Iters | Tokens | Time s | Epistemic | Fix-loop | Verify runs/fails |",
        "|---|---|---|---|---:|---:|---:|---|---|---|",
    ]
    for item in tasks:
        result = "PASS" if item.get("success") else "FAIL"
        epistemic = "yes" if item.get("used_epistemic") else "no"
        fix_loop = "yes" if item.get("used_fix_loop") else "no"
        lines.append(
            f"| {item.get('id')} | {item.get('category')} | {item.get('difficulty')} | {result} | "
            f"{item.get('iterations', 0)} | {item.get('total_tokens', 0)} | "
            f"{item.get('elapsed_seconds', 0)} | {epistemic} | {fix_loop} | "
            f"{item.get('verification_runs', 0)}/{item.get('verification_failures', 0)} |"
        )
    failed = [item for item in tasks if not item.get("success")]
    if failed:
        lines.extend(["", "## Failures", ""])
        for item in failed:
            lines.append(f"### {item.get('id')}")
            lines.append(f"- stop: `{item.get('stop_reason')}`")
            if item.get("error"):
                lines.append(f"- error: {item['error']}")
            if item.get("extra_check_errors"):
                for err in item["extra_check_errors"]:
                    lines.append(f"- extra check: {err}")
            report = (item.get("verification_report") or "").strip()
            if report:
                lines.append("```")
                lines.append(report)
                lines.append("```")
            lines.append("")
    return "\n".join(lines) + "\n"
