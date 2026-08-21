"""Merge hand-authored chunk JSONL files into mango_sft_1000.jsonl (no generation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "datasets" / "chunks"
OUT = ROOT / "datasets" / "mango_sft_1000.jsonl"
COPY = ROOT / "agent" / "python" / "mango_dataset" / "mango_sft_1000.jsonl"

FILES = (
    "agent_001.jsonl",
    "agent_002.jsonl",
    "agent_003.jsonl",
    "agent_004.jsonl",
    "cot.jsonl",
    "epistemic.jsonl",
    "finish.jsonl",
)


def main() -> int:
    rows: list[dict] = []
    for name in FILES:
        path = CHUNKS / name
        if not path.is_file():
            print(f"missing chunk: {path}", file=sys.stderr)
            return 1
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))

    if len(rows) != 1000:
        print(f"expected 1000 rows, got {len(rows)}", file=sys.stderr)
        return 1

    serialized = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows]
    if len(set(serialized)) != len(serialized):
        print("duplicate rows detected", file=sys.stderr)
        return 1

    text = "".join(s + "\n" for s in serialized)
    OUT.write_text(text, encoding="utf-8")
    COPY.parent.mkdir(parents=True, exist_ok=True)
    COPY.write_text(text, encoding="utf-8")

    stats = {
        "total": len(rows),
        "unique_lines": len(set(serialized)),
        "unique_user": len({r["messages"][1]["content"] for r in rows}),
        "unique_assistant": len({r["messages"][2]["content"] for r in rows}),
    }
    (ROOT / "datasets" / "mango_sft_1000_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf-8"
    )
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
