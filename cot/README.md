# CoT

Chain-of-Thought engine. **ReasoningState is separate from ContextState.**

Only a compressed summary is copied into the action prompt (`## Compressed reasoning summary`). The full reasoning object never goes through `build_prompt()`.

## ReasoningState

| Field | Meaning |
|-------|---------|
| `goal` | Task goal |
| `known_facts` | Confirmed observations |
| `decisions` | Choices already made |
| `assumptions` | Unverified beliefs |
| `failed_attempts` | What already failed |
| `open_questions` | Unresolved questions |
| `next_action` | Intended next step |

## Classification

`classify_reasoning_need(task, context_state) -> none | short | extended`

| Need | When | Model call |
|------|------|------------|
| `none` | Simple task, no failures | skipped |
| `short` | 1 failure or moderate complexity | compact JSON: `next_action`, `known_facts` |
| `extended` | ≥2 failures, many open questions, or a heavy task | fuller JSON update |

## Agent loop

```
classify_reasoning_need
        │
        ▼
run_reasoning_cycle  (none → no extra model call)
        │
        ▼
compress_reasoning_state → ContextState.reasoning_summary
        │
        ▼
build_prompt(context_state) → action model call
```

## Tests

```powershell
cd cot/python
pip install -e ".[dev]"
pytest -v
```
