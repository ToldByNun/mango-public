"""Merge v1 chunks + v3 language chunks into mango_sft_10000.jsonl."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATASETS = Path(__file__).resolve().parent
V1 = DATASETS / "chunks"
V3 = DATASETS / "chunks_v3"
REPORTS = DATASETS / "verify_reports"
OUT = DATASETS / "mango_sft_10000.jsonl"
COPY = REPO / "agent" / "python" / "mango_dataset" / "mango_sft_10000.jsonl"
STATS = DATASETS / "mango_sft_10000_stats.json"
INDEX = DATASETS / "catalog" / "index.jsonl"

V1_FILES = (
    "agent_001.jsonl",
    "agent_002.jsonl",
    "agent_003.jsonl",
    "agent_004.jsonl",
    "cot.jsonl",
    "epistemic.jsonl",
    "finish.jsonl",
)

TARGET_V3 = 9000


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_v1() -> list[dict]:
    rows: list[dict] = []
    for name in V1_FILES:
        rows.extend(_load_jsonl(V1 / name))
    return rows


def _load_v3() -> list[dict]:
    rows: list[dict] = []
    if not V3.is_dir():
        return rows
    for lang_dir in sorted(V3.iterdir()):
        if not lang_dir.is_dir() or lang_dir.name == "pilot":
            continue
        for path in sorted(lang_dir.glob("*.jsonl")):
            report = REPORTS / f"{path.stem}.json"
            if report.is_file():
                data = json.loads(report.read_text(encoding="utf-8"))
                if data.get("status") != "ok":
                    print(f"skip {path}: verify status={data.get('status')}", file=sys.stderr)
                    continue
            rows.extend(_load_jsonl(path))
    return rows


def main() -> int:
    v1 = _load_v1()
    v3 = _load_v3()
    if len(v1) != 1000:
        print(f"expected 1000 v1 rows, got {len(v1)}", file=sys.stderr)
        return 1
    if len(v3) != TARGET_V3:
        print(f"expected {TARGET_V3} v3 rows, got {len(v3)}", file=sys.stderr)
        return 1

    rows = v1 + v3
    serialized = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows]
    if len(set(serialized)) != len(serialized):
        print("duplicate rows", file=sys.stderr)
        return 1

    users = [r["messages"][1]["content"] for r in rows]
    assistants = [r["messages"][2]["content"] for r in rows]
    if len(set(users)) != len(users) or len(set(assistants)) != len(assistants):
        print("duplicate user/assistant", file=sys.stderr)
        return 1

    text = "".join(s + "\n" for s in serialized)
    OUT.write_text(text, encoding="utf-8")
    COPY.parent.mkdir(parents=True, exist_ok=True)
    COPY.write_text(text, encoding="utf-8")

    stats = {
        "total": len(rows),
        "v1_rows": len(v1),
        "v3_rows": len(v3),
        "unique_lines": len(set(serialized)),
        "unique_user": len(set(users)),
        "unique_assistant": len(set(assistants)),
    }
    if INDEX.is_file():
        index_rows = _load_jsonl(INDEX)
        stats["index_entries"] = len(index_rows)
        by_lang: dict[str, int] = {}
        by_wf: dict[str, int] = {}
        for e in index_rows:
            by_lang[e.get("lang", "?")] = by_lang.get(e.get("lang", "?"), 0) + 1
            by_wf[e.get("workflow", "?")] = by_wf.get(e.get("workflow", "?"), 0) + 1
        stats["by_lang"] = by_lang
        stats["by_workflow"] = by_wf

    STATS.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
