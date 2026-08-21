"""Load official SWE-bench Lite / Verified instances via the swebench package."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Official alias resolved by swebench.harness.utils.load_swebench_dataset
DEFAULT_DATASET = "lite"
DEFAULT_SPLIT = "test"
LITE_DATASET_HF = "SWE-bench/SWE-bench_Lite"


@dataclass(frozen=True)
class SweBenchInstance:
    """Thin wrapper around an official SWE-bench instance record."""

    data: dict[str, Any]
    local_repo_path: str | None = None

    @property
    def instance_id(self) -> str:
        return str(self.data["instance_id"])

    @property
    def repo(self) -> str:
        return str(self.data["repo"])

    @property
    def base_commit(self) -> str:
        return str(self.data["base_commit"])

    @property
    def problem_statement(self) -> str:
        return str(self.data.get("problem_statement") or "")

    @property
    def hints_text(self) -> str:
        return str(self.data.get("hints_text") or "")

    @classmethod
    def from_official(cls, record: dict[str, Any]) -> SweBenchInstance:
        local = record.get("local_repo_path")
        data = {key: value for key, value in record.items() if key != "local_repo_path"}
        return cls(
            data=data,
            local_repo_path=str(local) if local else None,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.data)
        if self.local_repo_path:
            payload["local_repo_path"] = self.local_repo_path
        return payload


def require_swebench() -> None:
    try:
        import swebench  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Official SWE-bench support requires the swebench package. "
            "Install with: pip install 'mango-agent[swebench]'"
        ) from exc


def load_instances(
    *,
    dataset_name: str = DEFAULT_DATASET,
    split: str = DEFAULT_SPLIT,
    fixture_path: Path | None = None,
    instance_ids: list[str] | None = None,
    limit: int | None = None,
) -> list[SweBenchInstance]:
    """Load instances using the official SWE-bench dataset loader."""
    if fixture_path:
        raw = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        records = raw if isinstance(raw, list) else [raw]
        if instance_ids:
            wanted = set(instance_ids)
            records = [record for record in records if str(record.get("instance_id")) in wanted]
        if limit is not None:
            records = records[:limit]
        return [SweBenchInstance.from_official(record) for record in records]

    require_swebench()
    from swebench.harness.utils import load_swebench_dataset

    source = str(fixture_path) if fixture_path else dataset_name
    records = load_swebench_dataset(source, split=split, instance_ids=instance_ids)
    if limit is not None:
        records = records[:limit]
    return [SweBenchInstance.from_official(record) for record in records]


def lite_instance_count(split: str = DEFAULT_SPLIT) -> int:
    """Return the number of instances in SWE-bench Lite for a split."""
    if split == "test":
        return 300
    if split == "dev":
        return 23
    raise ValueError(f"unknown SWE-bench Lite split: {split}")
