"""JSON and Markdown reports for SWE-bench runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_swebench_reports(
    payload: dict[str, Any],
    output_dir: Path,
    *,
    stamped: bool = True,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    json_text = json.dumps(payload, indent=2)
    md_text = render_swebench_markdown(payload)
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    json_path = latest_json
    md_path = latest_md
    if stamped:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_path = output_dir / f"swebench-{stamp}.json"
        md_path = output_dir / f"swebench-{stamp}.md"
        json_path.write_text(json_text, encoding="utf-8")
        md_path.write_text(md_text, encoding="utf-8")
    return json_path, md_path


def render_swebench_markdown(payload: dict[str, Any]) -> str:
    instances = list(payload.get("instances") or [])
    evaluated = payload.get("resolved") is not None
    lines = [
        "# Mango SWE-bench",
        "",
        f"- Created: {payload.get('created_at', '')}",
        f"- Dataset: `{payload.get('dataset_name', '')}` ({payload.get('split', '')})",
        f"- Model: `{payload.get('model_name', '')}`",
        f"- Instances: {payload.get('task_count', 0)}",
        f"- Non-empty patches: {payload.get('patch_count', 0)} "
        f"({float(payload.get('patch_rate') or 0) * 100:.1f}%)",
        f"- Reasoning cycles: {payload.get('total_reasoning_cycles', 0)}",
    ]
    if evaluated:
        lines.append(
            f"- Resolved (harness): {payload.get('resolved', 0)}/{payload.get('task_count', 0)} "
            f"({float(payload.get('pass_rate') or 0) * 100:.1f}%)"
        )
    lines.extend(
        [
            f"- Total tokens: {payload.get('total_tokens', 0)}",
            f"- Total time: {payload.get('total_elapsed_seconds', 0)}s",
            f"- Predictions: `{payload.get('predictions_path', '')}`",
            "",
            "| Instance | Repo | Patch | Resolved | Iters | Reason | Tokens | Time s | Bucket |",
            "|---|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for item in instances:
        patch = "yes" if item.get("patch_nonempty") else "no"
        resolved = item.get("resolved")
        if resolved is True:
            resolved_label = "yes"
        elif resolved is False:
            resolved_label = "no"
        else:
            resolved_label = "—"
        lines.append(
            f"| {item.get('instance_id')} | {item.get('repo')} | {patch} | {resolved_label} | "
            f"{item.get('iterations', 0)} | {item.get('reasoning_cycles', 0)} | "
            f"{item.get('total_tokens', 0)} | {item.get('elapsed_seconds', 0)} | "
            f"{(item.get('extra') or {}).get('failure_bucket', '')} |"
        )
    empty = [item for item in instances if not item.get("patch_nonempty")]
    buckets = dict(payload.get("failure_buckets") or {})
    if buckets:
        lines.extend(["", "## Failure Buckets", ""])
        for name, count in sorted(buckets.items()):
            lines.append(f"- `{name}`: {count}")
    if empty:
        lines.extend(["", "## Empty patches", ""])
        for item in empty:
            lines.append(f"- `{item.get('instance_id')}` stop=`{item.get('stop_reason')}`")
            if item.get("error"):
                lines.append(f"  - error: {item['error']}")
    return "\n".join(lines) + "\n"
