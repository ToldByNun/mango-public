#!/usr/bin/env python3
"""Build JSONL chunks for one language or pilot batch."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datasets.builders.generate import LANG_QUOTAS, build_and_write, generate_language
from datasets.builders.validate import validate_rows
from datasets.builders.verify import check_hard_pairs, write_report
import json


def build_pilot(out: Path) -> None:
    """~100 row pilot: hard pairs, security, mixed workflows."""
    out.mkdir(parents=True, exist_ok=True)
    scenarios = generate_language("python", 100, seed=0)
    rows = [s.to_row() for s in scenarios]
    index = [s.to_index_line() for s in scenarios]
    errs = validate_rows(rows)
    if errs:
        raise SystemExit(f"pilot validation: {errs[:10]}")
    path = out / "pilot.jsonl"
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows),
        encoding="utf-8",
    )
    idx_path = ROOT / "datasets" / "catalog" / "pilot_index.jsonl"
    idx_path.write_text("".join(json.dumps(i) + "\n" for i in index), encoding="utf-8")
    pair_errs = check_hard_pairs(index)
    write_report("pilot", pair_errs, len(rows))
    print(f"wrote {path} ({len(rows)} rows)")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("target", choices=[*LANG_QUOTAS.keys(), "pilot", "all"])
    p.add_argument("--out", type=Path, default=ROOT / "datasets" / "chunks_v3")
    p.add_argument("--no-verify", action="store_true")
    args = p.parse_args()

    if args.target == "pilot":
        build_pilot(args.out / "pilot")
        return 0

    if args.target == "all":
        for lang in LANG_QUOTAS:
            print(f"building {lang}...")
            build_and_write(lang, args.out / lang, verify=not args.no_verify)
        return 0

    build_and_write(args.target, args.out / args.target, verify=not args.no_verify)
    print(f"done {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
