# Epistemic

Isolated summarize turn that shares the **same ModelRunner** but never the main agent's chat.

## ask_epistemic

The runner:

1. Resolves concrete symbols from the question (`collections` → `deque`, `threading` → `Lock`, `time` → `monotonic`).
2. Loads each via `importlib` / `inspect` (source or C-extension docstring).
3. Asks the model **once** to write a targeted usage brief (import, snippet, pitfalls). Nested thoughts/lookups are **not** forwarded to the Mango transcript — they stay inside the “Asked epistemic sub-agent” bubble.

The main agent receives `EpistemicResult.to_compact_dict()` only.

## Tests

```powershell
cd epistemic/python
pip install -e ".[dev]"
pytest -v
```
