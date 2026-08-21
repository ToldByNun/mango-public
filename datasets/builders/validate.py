from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def sentence_count(text: str) -> int:
    compact = " ".join(text.split()).strip()
    parts = SENTENCE_RE.split(compact)
    return len([p for p in parts if p.strip()])


def classify_row(row: dict[str, Any]) -> str:
    msgs = row["messages"]
    assistant = msgs[2]["content"]
    system = msgs[0]["content"]
    if "thought 1:" in assistant and "thought summary:" in assistant:
        return "cot_cycle"
    if "<tool_call=" in assistant:
        return "agent_action"
    if "API Agent" in system:
        return "epistemic_answer"
    return "agent_finish"


def validate_rows(
    rows: list[dict[str, Any]],
    *,
    existing_users: set[str] | None = None,
    existing_assistants: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    users: set[str] = set(existing_users or ())
    assistants: set[str] = set(existing_assistants or ())
    serialized: set[str] = set()

    for i, row in enumerate(rows):
        prefix = f"row {i}"
        if set(row.keys()) != {"messages"}:
            errors.append(f"{prefix}: bad top-level keys")
            continue
        msgs = row["messages"]
        if [m["role"] for m in msgs] != ["system", "user", "assistant"]:
            errors.append(f"{prefix}: bad roles")
            continue
        s = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        if s in serialized:
            errors.append(f"{prefix}: duplicate serialized row")
        serialized.add(s)

        user = msgs[1]["content"]
        assistant = msgs[2]["content"]
        if user in users:
            errors.append(f"{prefix}: duplicate user")
        if assistant in assistants:
            errors.append(f"{prefix}: duplicate assistant")
        users.add(user)
        assistants.add(assistant)

        kind = classify_row(row)
        if kind == "cot_cycle":
            for line in ("thought 1:", "thought 2:", "thought 3:", "thought 4:", "thought summary:"):
                if line not in assistant:
                    errors.append(f"{prefix}: missing {line}")
        elif kind == "agent_action":
            if assistant.count("<tool_call=") != 1:
                errors.append(f"{prefix}: expected exactly one tool_call")
            thought = assistant.split("\n", 1)[0]
            n = sentence_count(thought)
            if n < 3 or n > 5:
                errors.append(f"{prefix}: agent thought sentences={n}")
        elif kind == "epistemic_answer":
            if "<tool_call=" in assistant:
                errors.append(f"{prefix}: epistemic must not have tool_call")
        else:
            if "<tool_call=" in assistant:
                errors.append(f"{prefix}: finish must not have tool_call")
            if sentence_count(assistant) != 3:
                errors.append(f"{prefix}: finish needs 3 sentences got {sentence_count(assistant)}")
            if "./..." in assistant or "busted ." in assistant:
                errors.append(f"{prefix}: finish sentence-split hazard")

    return errors


def validate_jsonl_path(path: Path, **kwargs: Any) -> list[str]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return validate_rows(rows, **kwargs)


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if not args:
        print("usage: validate.py <chunk.jsonl> [chunk2.jsonl ...]", file=sys.stderr)
        return 1
    ok = True
    for arg in args:
        path = Path(arg)
        errs = validate_jsonl_path(path)
        if errs:
            ok = False
            print(f"{path}: {len(errs)} errors")
            for e in errs[:20]:
                print(f"  {e}")
        else:
            lines = len(path.read_text(encoding="utf-8").splitlines())
            print(f"{path}: OK ({lines} rows)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
