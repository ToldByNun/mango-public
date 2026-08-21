# Agent

Full main loop: `/runtime` + `/tools` + `/context` + `/cot` + `/epistemic` + `/codeintel` + `/verification`.

**Language:** Python

## Loop

```
Task
  → ContextState initialized (goal, tools, budget)
  → each iteration, until done / iteration cap / time cap:
        classify_reasoning_need → maybe run_reasoning_cycle (capped)
        compress_reasoning_state → ContextState.reasoning_summary
        build_prompt(ContextState) → action model
        tools: read/edit/write, codebase_lookup, ask_epistemic, …
        after write_file / edit_file / edit_symbol → run_verification() immediately
        on failure → compact errors into ContextState → CoT → fix (max_fix_attempts)
```

`codebase_lookup` finds symbols/files instead of blindly reading. `ask_epistemic` spawns an isolated sub-agent (own context, shared model) for API questions.

System prompts live in [`prompts/`](../prompts/) (`agent.md`, `swebench.md`, `epistemic.md`, `title.md`, `cot.md`). Edit the markdown; the agent loads them at startup.

## Limits (all levels)

| Knob | Default | Applies to |
|---|---|---|
| `max_iterations` | 10 | main loop |
| `max_runtime_seconds` | 300 | main + nested (shared deadline) |
| `max_reasoning_cycles` | 20 | CoT model calls |
| `max_fix_attempts` | 5 | verification failures |
| `max_epistemic_iterations` | 6 | API sub-agent |
| `max_prompt_chars` | 24000 | action prompt window |

## Setup

```powershell
cd agent/python
python -m venv .venv
.venv\Scripts\activate
pip install -e ..\..\runtime\python
pip install -e ..\..\tools\python
pip install -e ..\..\context\python
pip install -e ..\..\cot\python
pip install -e ..\..\epistemic\python
pip install -e ..\..\codeintel\python
pip install -e ..\..\verification\python
pip install -e ".[dev]"
```

```python
from mango_agent import Orchestrator, AgentLimits

orch = Orchestrator(model_runner, workspace=".", limits=AgentLimits(max_iterations=12))
result = orch.run("Implement discount() in app/pricing.py")
print(result.metrics.format_log("task", stop_reason=result.stop_reason.value))
```

## Coding benchmark

15 isolated Python tasks, **5 easy / 5 medium / 5 hard**. Each workspace starts with failing tests; success is `run_verification()` plus optional file-content checks. Action turns generate a short unconstrained thought, then apply GBNF only after `<tool_call=`.

```powershell
python -m mango_agent.benchmark --list
python -m mango_agent.benchmark --output-dir benchmark_reports
python -m mango_agent.benchmark --tasks feature_clamp,bugfix_inclusive_sum
python -m mango_agent.benchmark --no-grammar
```

Writes timestamped JSON + Markdown (`latest.json` / `latest.md`) with pass/fail, iterations, tokens, wall time, epistemic use, and verification fix-loop use. Re-run after framework changes to spot regressions.

## SWE-bench Lite (official)

Run Mango on the **official [SWE-bench Lite](https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite)** benchmark (300 real GitHub issues). Uses the `swebench` package for dataset loading and the official Docker harness for scoring.

```powershell
pip install "mango-agent[swebench]"

# List official Lite instances
python -m mango_agent.benchmark.swebench --list

# Run one official instance with your local GGUF model
python -m mango_agent.benchmark.swebench `
  --dataset lite `
  --instances sympy__sympy-20590 `
  --output-dir swebench_reports

# Small batch from SWE-bench Lite
python -m mango_agent.benchmark.swebench `
  --dataset lite `
  --limit 5 `
  --output-dir swebench_reports

# Generate predictions + score with official Docker harness
python -m mango_agent.benchmark.swebench `
  --dataset lite `
  --limit 10 `
  --evaluate `
  --eval-workers 4 `
  --output-dir swebench_reports

# Re-score an existing predictions file
python -m mango_agent.benchmark.swebench `
  --evaluate-only `
  --predictions swebench_reports/predictions.json `
  --dataset lite `
  --output-dir swebench_reports
```

### Baseline (10 instances, optimize against this)

Curated set spanning 10 major Python repos (incl. `sympy__sympy-20590` for harness validation):

| Instance | Repo |
|---|---|
| astropy__astropy-12907 | astropy/astropy |
| django__django-10914 | django/django |
| matplotlib__matplotlib-18869 | matplotlib/matplotlib |
| pallets__flask-4045 | pallets/flask |
| psf__requests-1963 | psf/requests |
| pydata__xarray-3364 | pydata/xarray |
| pylint-dev__pylint-5859 | pylint-dev/pylint |
| pytest-dev__pytest-11143 | pytest-dev/pytest |
| scikit-learn__scikit-learn-10297 | scikit-learn/scikit-learn |
| sympy__sympy-20590 | sympy/sympy |

```powershell
# 1) First baseline run (patches only, no Docker)
python -m mango_agent.benchmark.swebench --baseline --output-dir swebench_reports/baseline

# 2) Score with official harness (Docker required)
python -m mango_agent.benchmark.swebench --baseline --evaluate --output-dir swebench_reports/baseline

# 3) Pin current scores as reference
python -m mango_agent.benchmark.swebench --baseline --evaluate --save-reference --output-dir swebench_reports/baseline

# 4) After optimizations — compare against reference
python -m mango_agent.benchmark.swebench --baseline --evaluate `
  --compare swebench_reports/baseline/reference.json `
  --output-dir swebench_reports/baseline

# Or use the helper script
.\scripts\run_swebench_baseline.ps1 -Evaluate -Compare
```

Comparison writes `comparison.md` and `comparison.json` next to `latest.json`.

### Docker setup (required for `--evaluate`)

Official SWE-bench scoring needs **Docker Desktop + WSL2** on Windows. Run **PowerShell as Administrator**:

```powershell
cd agent/python
# If scripts are blocked by execution policy:
.\scripts\setup_swebench_windows.cmd
# or: powershell -ExecutionPolicy Bypass -File .\scripts\setup_swebench_windows.ps1
```

Reboot if prompted, start Docker Desktop, then:

```powershell
.\scripts\run_swebench_baseline.ps1 -Evaluate -SaveReference
```

Unit tests (no model/Docker):

```powershell
pytest tests/test_swebench_harness.py -v
```

Live HF load test (network):

```powershell
pytest tests/test_swebench_harness.py -v -m swebench_live
```

Reports land in `swebench_reports/` with patch rate and, when `--evaluate` is used, official harness resolve rate. Predictions are compatible with `python -m swebench.harness.run_evaluation`.

## Tests

```powershell
pytest tests/test_agent_loop.py tests/test_verification_fix_loop.py tests/test_main_loop_e2e.py tests/test_benchmark_harness.py tests/test_swebench_harness.py -v
```
