"""Merge v1 + v2 chunks into mango_sft_2000.jsonl."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "datasets" / "chunks"
CHUNKS2 = ROOT / "datasets" / "chunks2"
OUT = ROOT / "datasets" / "mango_sft_2000.jsonl"
COPY = ROOT / "agent" / "python" / "mango_dataset" / "mango_sft_2000.jsonl"
STATS = ROOT / "datasets" / "mango_sft_2000_stats.json"

V1_FILES = (
    "agent_001.jsonl",
    "agent_002.jsonl",
    "agent_003.jsonl",
    "agent_004.jsonl",
    "cot.jsonl",
    "epistemic.jsonl",
    "finish.jsonl",
)

V2_FILES = (
    "agent_ml_001.jsonl",
    "agent_ml_002.jsonl",
    "agent_ml_003.jsonl",
    "agent_ml_004.jsonl",
    "cot_ml.jsonl",
    "epistemic_ml.jsonl",
    "finish_ml.jsonl",
)


def _load_dir(directory: Path, names: tuple[str, ...]) -> list[dict]:
    rows: list[dict] = []
    for name in names:
        path = directory / name
        if not path.is_file():
            print(f"missing chunk: {path}", file=sys.stderr)
            raise SystemExit(1)
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main() -> int:
    rows = _load_dir(CHUNKS, V1_FILES) + _load_dir(CHUNKS2, V2_FILES)
    if len(rows) != 2000:
        print(f"expected 2000 rows, got {len(rows)}", file=sys.stderr)
        return 1

    serialized = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows]
    if len(set(serialized)) != len(serialized):
        print("duplicate rows detected", file=sys.stderr)
        return 1

    users = [r["messages"][1]["content"] for r in rows]
    assistants = [r["messages"][2]["content"] for r in rows]
    if len(set(users)) != len(users) or len(set(assistants)) != len(assistants):
        print("duplicate user or assistant content", file=sys.stderr)
        return 1

    text = "".join(s + "\n" for s in serialized)
    OUT.write_text(text, encoding="utf-8")
    COPY.parent.mkdir(parents=True, exist_ok=True)
    COPY.write_text(text, encoding="utf-8")

    stats = {
        "total": len(rows),
        "unique_lines": len(set(serialized)),
        "unique_user": len(set(users)),
        "unique_assistant": len(set(assistants)),
        "v1_rows": 1000,
        "v2_rows": 1000,
    }
    STATS.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
