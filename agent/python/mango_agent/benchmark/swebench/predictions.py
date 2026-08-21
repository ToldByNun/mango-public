"""Write SWE-bench prediction files for the official evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mango_agent.benchmark.swebench.types import SweBenchOutcome


def prediction_record(outcome: SweBenchOutcome, *, model_name: str) -> dict[str, str]:
    return {
        "instance_id": outcome.instance_id,
        "model_patch": outcome.model_patch or "",
        "model_name_or_path": model_name,
    }


def write_predictions(
    outcomes: list[SweBenchOutcome],
    path: Path,
    *,
    model_name: str,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [prediction_record(item, model_name=model_name) for item in outcomes]
    if path.suffix == ".jsonl":
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    else:
        path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return path


def load_predictions(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, list):
        return data
    raise ValueError(f"predictions file must contain a JSON array: {path}")
