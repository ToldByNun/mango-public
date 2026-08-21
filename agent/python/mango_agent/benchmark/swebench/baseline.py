"""SWE-bench Lite baseline set and run comparison helpers."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any


def bundled_baseline_path() -> Path:
    root = resources.files("mango_agent.benchmark.swebench") / "baseline.json"
    return Path(str(root))


def load_baseline_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or bundled_baseline_path()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"baseline config must be a JSON object: {config_path}")
    ids = payload.get("instance_ids")
    if not isinstance(ids, list) or not ids:
        raise ValueError(f"baseline config missing instance_ids: {config_path}")
    return payload


def baseline_instance_ids(path: Path | None = None) -> list[str]:
    return [str(item) for item in load_baseline_config(path)["instance_ids"]]


def compare_reports(current: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    cur_resolved = current.get("resolved")
    ref_resolved = reference.get("resolved")
    cur_rate = current.get("pass_rate")
    ref_rate = reference.get("pass_rate")
    cur_patch = current.get("patch_rate")
    ref_patch = reference.get("patch_rate")
    cur_tokens = int(current.get("total_tokens") or 0)
    ref_tokens = int(reference.get("total_tokens") or 0)
    cur_time = float(current.get("total_elapsed_seconds") or 0)
    ref_time = float(reference.get("total_elapsed_seconds") or 0)

    def delta(cur: float | None, ref: float | None) -> float | None:
        if cur is None or ref is None:
            return None
        return round(cur - ref, 4)

    per_instance: list[dict[str, Any]] = []
    ref_by_id = {str(item.get("instance_id")): item for item in reference.get("instances") or []}
    for item in current.get("instances") or []:
        iid = str(item.get("instance_id"))
        ref_item = ref_by_id.get(iid, {})
        cur_ok = item.get("resolved")
        ref_ok = ref_item.get("resolved")
        changed = cur_ok != ref_ok and cur_ok is not None and ref_ok is not None
        if changed or item.get("patch_nonempty") != ref_item.get("patch_nonempty"):
            per_instance.append(
                {
                    "instance_id": iid,
                    "resolved": {"current": cur_ok, "reference": ref_ok},
                    "patch_nonempty": {
                        "current": item.get("patch_nonempty"),
                        "reference": ref_item.get("patch_nonempty"),
                    },
                }
            )

    return {
        "baseline_name": reference.get("baseline_name") or reference.get("suite"),
        "resolved": {"current": cur_resolved, "reference": ref_resolved, "delta": delta(cur_resolved, ref_resolved)},
        "pass_rate": {"current": cur_rate, "reference": ref_rate, "delta": delta(cur_rate, ref_rate)},
        "patch_rate": {"current": cur_patch, "reference": ref_patch, "delta": delta(cur_patch, ref_patch)},
        "total_tokens": {"current": cur_tokens, "reference": ref_tokens, "delta": cur_tokens - ref_tokens},
        "total_elapsed_seconds": {
            "current": cur_time,
            "reference": ref_time,
            "delta": round(cur_time - ref_time, 4),
        },
        "changed_instances": per_instance,
    }


def render_comparison(comparison: dict[str, Any]) -> str:
    lines = [
        "# SWE-bench baseline comparison",
        "",
        f"- Resolved: {comparison['resolved']['current']}/{comparison.get('task_count', '?')} "
        f"(ref {comparison['resolved']['reference']}, Δ {comparison['resolved']['delta']})",
        f"- Pass rate: {float(comparison['pass_rate']['current'] or 0) * 100:.1f}% "
        f"(ref {float(comparison['pass_rate']['reference'] or 0) * 100:.1f}%, "
        f"Δ {float(comparison['pass_rate']['delta'] or 0) * 100:+.1f} pp)",
        f"- Patch rate: {float(comparison['patch_rate']['current'] or 0) * 100:.1f}% "
        f"(ref {float(comparison['patch_rate']['reference'] or 0) * 100:.1f}%)",
        f"- Tokens: {comparison['total_tokens']['current']} "
        f"(ref {comparison['total_tokens']['reference']}, Δ {comparison['total_tokens']['delta']:+d})",
        f"- Time: {comparison['total_elapsed_seconds']['current']}s "
        f"(ref {comparison['total_elapsed_seconds']['reference']}s, "
        f"Δ {comparison['total_elapsed_seconds']['delta']:+.2f}s)",
    ]
    changed = comparison.get("changed_instances") or []
    if changed:
        lines.extend(["", "## Changed instances", ""])
        for item in changed:
            lines.append(f"- `{item['instance_id']}` resolved {item['resolved']}")
    return "\n".join(lines) + "\n"
