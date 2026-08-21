import json
import re
from collections import Counter
from pathlib import Path

p = Path(__file__).parent / "mango_sft_10000.jsonl"
rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

diffs = Counter()
multi_file_diffs = Counter()
for r in rows:
    a = r["messages"][2]["content"]
    for m in re.finditer(r'"old_string":"(.*?)","new_string":"(.*?)"', a):
        diffs[f"{m.group(1)} -> {m.group(2)}"] += 1

print("unique diffs:", len(diffs), "/ total:", sum(diffs.values()))
print("top 15 repeated:")
for d, c in diffs.most_common(15):
    print(f"  {c}x: {d[:150]}")

# Python syntax in non-Python rows
syntax_mix = 0
for r in rows:
    a = r["messages"][2]["content"]
    u = r["messages"][1]["content"]
    is_non_py = any(ext in u or ext in a for ext in (".c\n", ".cpp", ".rs", ".go", ".js", ".ts"))
    has_py = any(kw in a for kw in ("self.", "def ", "import ", "pickle.", "asyncio."))
    if is_non_py and has_py and "python" not in u.lower()[:50]:
        syntax_mix += 1

print(f"\npython-syntax-in-non-python: {syntax_mix}")
