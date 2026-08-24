"""Shuffle deck for SWE-bench: random order, each instance once per cycle."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from mango_agent.benchmark.swebench.instances import SweBenchInstance, lite_instance_count


def shuffle_state_path(output_dir: Path) -> Path:
    return Path(output_dir) / "shuffle_state.json"


def _pool_key(instance_ids: list[str]) -> str:
    return "|".join(sorted(instance_ids))


def load_shuffle_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_shuffle_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def max_count_for_dataset(dataset_name: str, split: str) -> int:
    if dataset_name in {"lite", "SWE-bench/SWE-bench_Lite"}:
        return lite_instance_count(split)
    return 300


def validate_count(count: int, *, dataset_name: str, split: str) -> int:
    if count < 1:
        raise ValueError("--count must be at least 1")
    ceiling = max_count_for_dataset(dataset_name, split)
    if count > ceiling:
        raise ValueError(f"--count must be <= {ceiling} for dataset {dataset_name!r} (split={split})")
    return count


def pick_shuffled_instances(
    pool: list[SweBenchInstance],
    *,
    count: int,
    state_path: Path,
    dataset_name: str,
    split: str,
    seed: int | None = None,
    reset: bool = False,
) -> tuple[list[SweBenchInstance], dict[str, Any]]:
    """Pop ``count`` instances from a shuffled deck (no repeats until cycle completes)."""
    if not pool:
        return [], {"remaining": [], "cycle": 0, "completed": []}

    ids = [item.instance_id for item in pool]
    by_id = {item.instance_id: item for item in pool}
    key = _pool_key(ids)

    state = None if reset else load_shuffle_state(state_path)
    if state is None or state.get("pool_key") != key:
        state = {"pool_key": key, "dataset": dataset_name, "split": split, "cycle": 0, "remaining": [], "completed": []}

    remaining: list[str] = list(state.get("remaining") or [])
    if not remaining:
        rng = random.Random(seed if seed is not None else state.get("cycle", 0))
        remaining = list(ids)
        rng.shuffle(remaining)
        state["cycle"] = int(state.get("cycle") or 0) + 1
        state["completed"] = []

    take = min(count, len(remaining))
    picked_ids = remaining[:take]
    state["remaining"] = remaining[take:]
    completed = list(state.get("completed") or [])
    completed.extend(picked_ids)
    state["completed"] = completed

    picked = [by_id[iid] for iid in picked_ids if iid in by_id]
    save_shuffle_state(state_path, state)
    return picked, state


def deck_status(state_path: Path) -> dict[str, Any] | None:
    state = load_shuffle_state(state_path)
    if not state:
        return None
    remaining = list(state.get("remaining") or [])
    completed = list(state.get("completed") or [])
    return {
        "cycle": int(state.get("cycle") or 0),
        "remaining": len(remaining),
        "completed_this_cycle": len(completed),
        "done": not remaining,
    }
