"""Compare two baseline JSON files (A0a / A0c / A5).

Usage:
  python -m mango_agent.metrics_compare a.json b.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from mango_agent.metrics import compare_metrics, load_metrics_json


def _flatten(payload: dict[str, Any]) -> dict[str, Any]:
    if "aggregates" in payload and isinstance(payload["aggregates"], dict):
        flat = dict(payload["aggregates"])
        flat["kind"] = payload.get("kind")
        return flat
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Mango baseline metric files")
    parser.add_argument("before")
    parser.add_argument("after")
    args = parser.parse_args(argv)
    a = _flatten(load_metrics_json(args.before))
    b = _flatten(load_metrics_json(args.after))
    # Also compare mean edit_fail_rate from runs if present.
    for label, src in (("before", args.before), ("after", args.after)):
        raw = load_metrics_json(src)
        runs = raw.get("runs") if isinstance(raw, dict) else None
        if isinstance(runs, list) and runs:
            rates = [float(r.get("edit_fail_rate") or 0) for r in runs if isinstance(r, dict)]
            repeats = [int(r.get("identical_tool_repeat_max") or 0) for r in runs if isinstance(r, dict)]
            target = a if label == "before" else b
            target.setdefault("edit_fail_rate", sum(rates) / len(rates))
            target.setdefault("identical_tool_repeat_max", sum(repeats) / len(repeats))
    delta = compare_metrics(a, b)
    print(json.dumps(delta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
