from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATASET = ROOT / "datasets" / "mango_sft_10000.jsonl"
INDEX = ROOT / "datasets" / "catalog" / "index_combined.jsonl"


def _load_index() -> list[dict]:
    catalog = ROOT / "datasets" / "catalog"
    rows: list[dict] = []
    for path in sorted(catalog.glob("index_*.jsonl")):
        if path.name == "index_combined.jsonl":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def test_merged_10000_exists_and_unique() -> None:
    assert DATASET.is_file(), f"missing {DATASET}"
    lines = DATASET.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10000

    serialized: set[str] = set()
    users: set[str] = set()
    assistants: set[str] = set()

    for line in lines:
        row = json.loads(line)
        s = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        assert s not in serialized
        serialized.add(s)
        user = row["messages"][1]["content"]
        assistant = row["messages"][2]["content"]
        assert user not in users
        assert assistant not in assistants
        users.add(user)
        assistants.add(assistant)


def test_index_covers_v3() -> None:
    index = _load_index()
    assert len(index) >= 9000
