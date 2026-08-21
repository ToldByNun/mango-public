from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

p = Path(__file__).parent / "mango_sft_10000.jsonl"
rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
fence = chr(96) * 3
code = sum(1 for r in rows if fence in r["messages"][2]["content"] or "write_file" in r["messages"][2]["content"])
langs = Counter()
workflows = Counter()
for line in Path(__file__).parent.joinpath("catalog", "index.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        e = json.loads(line)
        langs[e.get("lang", "?")] += 1
        workflows[e.get("workflow", "?")] += 1
print("rows", len(rows), "code_rows", code)
print("index langs", langs.most_common())
print("index workflows", workflows.most_common())
