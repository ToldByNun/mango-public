# Verification

Treat generated code as a hypothesis until the environment confirms it.

**Language:** Python

## API

```python
from mango_verification import run_verification, load_verification_config

result = run_verification(project_path, config=None)
# result.success, result.build_output, result.test_output, result.diagnostics
print(result.compact_report())
```

Steps (each skipped when the command is empty):

1. `build_step(project_path)` — run the configured build command
2. `test_step(project_path)` — run tests and parse passed/failed counts, failed names, messages
3. `diagnostics_step(project_path)` — optional linter/compiler output with file+line

## Per-project config

Looked up under the project root (first match wins):

- `mango.verify.yaml` / `.yml` / `.json`
- `.mango/verify.yaml` / `.yml` / `.json`
- legacy: `mango.verify.*` / `.mango/verify.*`

```yaml
build:
  command: npm run build
  timeout: 120
test:
  command: python -m pytest -q --tb=short
  timeout: 60
diagnostics:
  command: ruff check .
```

JSON equivalent: `{"test": {"command": "cargo test", "timeout": 60}}`.

You can also pass a dict or `VerificationConfig` as the `config` argument.

## Agent fix-loop

After a successful `write_file` / `edit_file` / `edit_symbol`, the agent runtime calls `run_verification()`.

- On failure: a compact report (not the raw log) is stored on `ContextState.verification_feedback` and as a `verification` tool result, then the CoT cycle runs and the agent tries again.
- Cap: `max_fix_attempts` (default 5). After that the agent stops with `StopReason.VERIFICATION_FAILED` and a report for the user.
- A no-tool “final answer” is rejected while the last verification failed.

```
verification/
└── python/mango_verification/
    ├── verifier.py      # run_verification + steps
    ├── parsers.py       # pytest / compiler diagnostics
    ├── config.py
    └── runners/command.py
```
