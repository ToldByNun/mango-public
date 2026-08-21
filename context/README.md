# Context

Prompt window: rebuild a compact prompt from `ContextState` each turn instead of appending the full history.

**Language:** Python (assembly + truncation). C++ stubs remain for a later token-accurate budget.

## ContextState

| Field | Role |
|-------|------|
| `goal` | Current task — never truncated |
| `constraints` | Hard limits / style rules |
| `relevant_files` | Paths touched this session |
| `previous_actions` | One-line action log |
| `tool_results` | Compact tool output (oldest summarized first) |
| `memory` | Deterministic facts (AST file slices, last write/verify) |

## AST slices

Raw file contents never go to the worker. `slice_source()` keeps the relevant signature plus 5 body lines (line length capped). Unfocused helpers collapse to `def foo(...): ...`.

## Budget guard

Before each model call:

1. Replace **old** tool-result bodies with one-line `[compact]` summaries
2. Keep the newest results as AST slices, not dumps
3. Render `## Memory` with current file slices
4. If still over `max_chars`, shrink/omit oldest leftovers

The goal section is not shortened.

## Usage

```python
from mango_context import ContextEngine, ContextBudget, build_prompt

engine = ContextEngine(
    "Replace Mango with Agent in greeting.txt",
    system_prompt="You are Mango.",
    tools=[("read_file", "Read a file"), ("edit_file", "Replace a snippet")],
    budget=ContextBudget(max_chars=24_000),
)
engine.record_turn(1, model_output="...", tool_results=[...])
prompt = engine.build_prompt()
```

## Tests

```powershell
cd context/python
pip install -e ".[dev]"
pytest -v
```
