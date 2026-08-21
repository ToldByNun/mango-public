# Mango

Local coding agent for **small GGUF models**. One loaded model, many specialized contexts (coder, API researcher, summarizer).

Repo: [github.com/ToldByNun/mango-public](https://github.com/ToldByNun/mango-public)

A 12B local model cannot afford Aider-style repo maps or long framework essays. GUI prompts are short; GBNF and the executor enforce the workflow. `ask_epistemic` returns a deterministic usage card for known stdlib (no nested generate, so the main KV cache stays intact). Unknown libraries still get one isolated summarize turn.

Visual Docker/WASM sandboxing in the GUI is not built yet.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Electron (Mango)                                                │
│  sessions · transcript · composer · model picker                 │
└────────────────────────────┬────────────────────────────────────┘
                             │ JSONL stdin/stdout
┌────────────────────────────▼────────────────────────────────────┐
│  Python sidecar  (`python -m mango_agent.serve`)                 │
│  Orchestrator → Agent loop                                       │
│    Context · CoT · Tools · Epistemic · CodeIntel · Verification  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                      Runtime (llama.cpp / GGUF)
                      one model instance, shared
```

**Electron never talks to the model.** It sends `{method: "run", params: {goal, workspace, session_id}}` and renders `agent.token`, `agent.tool`, `agent.file`, `agent.final` events. The sidecar owns the workspace, tools, and finish criteria.

The Mango **source tree is rejected as a workspace**. If the UI is opened on this repo, the sidecar falls back to `~/.mango/workspaces/<session>` so the agent cannot rewrite its own framework.

### Process split (why)

| Layer | Language | Why |
|---|---|---|
| Inference | C++ (llama.cpp) + Python `ModelRunner` | GGUF load, GPU, sampling, GBNF. One instance; epistemic sub-agents share it. |
| Agent loop | Python | Tools, pytest, SQLite index, compile(). Restart the sidecar after Python/prompt changes. |
| UI | TypeScript / Electron | Streaming transcript, follow-up composition, model logos. Restart Electron only for UI. |

### Shared model, different contexts

A context is **not** a second model. It is a system prompt, a tool whitelist, a GBNF grammar, and runner flags:

| Context | Used for | Tools | Runner flags |
|---|---|---|---|
| GUI coder | Mango sessions | declare → epistemic → write/edit/test | `plan_apis_first`, `require_tools`, `task_wants_tests`, 192 thought tokens, 2048 tool tokens |
| Epistemic sub-agent | Targeted usage brief | runner loads symbols; one summarize turn | nested events stay inside the parent bubble |
| Finish summarizer | User-facing last message | none | `prompts/summary.md` |
| SWE-bench | Official GitHub issues | `edit_file` / `edit_symbol`, no `write_file` | no plan gate |

CoT (chain-of-thought) is a **short JSON cycle** before an action, used on SWE-bench. **GUI turns it off** (`max_reasoning_cycles=0`): a second generate dumps code into “thought” and starves the GBNF tool call. The visible thought is the unconstrained prefix before `<tool_call=…>` (`thought_max_tokens=192`). The constrained tool tail defaults to **384 tokens** — enough for `ask_epistemic`, not for JSON-escaped `write_file` of a real module. The GUI sidecar sets `tool_max_tokens=2048` and raises that to 3072 after a truncated JSON so the model does not loop on “I will create the file” forever.

## Main loop (what actually runs)

```
goal
  → (GUI) prepend original request + last summary if this is a follow-up
  → until done / 20 iterations / 600s:
        thought (unconstrained, 192 tokens) + GBNF tool call
        execute tools (or BLOCKED)
        compile() each mutated .py
        pytest in the background after a mutation
        if tests fail → feedback, lock grammar to edit + run_tests, retry (max 3 real failures)
        if concurrent code without thread tests → demand ThreadPoolExecutor tests
        if lock/thread mutation → require read_file before finish (design review)
        if lock coarsened (per-client → one global Lock) → extra STOP message
  → summary.md (not “All tests passed.”)
```

**Compile is not runtime.** `compile(source, "exec")` only checks that the file parses. Wrong pandas kwargs, missing CSV columns, and races are invisible until pytest. That is why the runner treats tests as the only execution check, and why “the script compiled” is never a finish condition.

## Design decisions

These exist because small local models fail in predictable ways. Each one is **runner-enforced**, not a suggestion in `agent.md`.

### 1. Plan gate: declare APIs, then look them up, then write

**Problem:** The model writes `argparse.add_argument(...)` with a signature it invented. Compile still succeeds.

**Decision:** GUI blocks `write_file` until:

1. `declare_apis` lists every import (stdlib included: `argparse`, `pathlib`, `json`, …).
2. `ask_epistemic` asks a question that **contains every declared name**. The runner loads each concrete symbol (`deque`, `Lock`, `monotonic`, …) itself, then one isolated summarize turn writes a **targeted** usage brief (import, snippet, complexity). Nested lookups are not extra chat lines — they stay inside “Asked epistemic sub-agent”. Module dumps and `deque(/, *args, **kwargs)` are rejected.

GBNF only allows the current step. If the model emits `write_file` too early, the executor returns `BLOCKED by the runner` and does not create the file.

SWE-bench turns this **off**. Those tasks patch existing trees; `write_file` is disabled so the model cannot create a parallel implementation.

### 2. Closed-loop tests (no `/test`)

**Problem:** Tools like Aider apply a patch and wait for the human. The patch can look fine and still be wrong.

**Decision:** After every successful mutation the sidecar runs pytest in the workspace (`test_*.py`, 60s timeout, isolated `PYTHONPATH`). The user still sees a “Running tests…” badge; they do not have to start the run.

- No `test_*.py` yet → demand tests; **does not** burn a retry.
- Tests fail → fix loop, grammar locked to mutating tools + `run_tests`.
- **5 failed pytest runs** → stop and summarize (red is allowed). Infinite retry until `max_iterations` was worse than showing the failure.

### 3. Happy-path tests are not enough for concurrent code

**Problem:** A rate limiter with a `Lock` passes `test_allow()` and still has a race, or serializes every client behind one lock.

**Decision:** If implementation files mention `threading` / `Lock` / `asyncio` / `concurrent.futures`, tests must mention `ThreadPoolExecutor` or `threading.Thread` (8+ workers, high-volume case). The runner nudges twice, then gives up so the loop cannot hang forever.

Green tests still do not prove lock **granularity**. See the next point.

### 4. Design review: doubt the last edit

**Problem:** The model “cleaned up” per-client locks into `self.lock = Lock()`. Behavior stayed correct; unrelated clients now block each other. Pytest stayed green.

**Decision:** After a concurrent or lock-structure mutation, finishing is blocked until the agent `read_file`s the implementation **again**. The next generation sees the file plus a STOP if locks were coarsened. Prompt text is not enough; the runner withholds complete.

### 5. Repo map as a graph, not a text dump

**Problem:** A Tree-sitter “repo map” of every class saturates a 8–12k context window and still misses “who imports this?”

**Decision:** CodeIntel indexes files, symbols, refs, and resolved imports in SQLite. `codebase_lookup` / `impact()` returns a **neighborhood**: definition files, importers, call sites, related `test_*.py`. After a mutation the runner injects a few lines (`used by app/main.py; tests: tests/test_util.py`) instead of whole files. Slicing keeps signatures + short bodies.

### 6. Adaptive diffs: JSON first, fuzzy match, then whole file

**Problem:** Local models break `<<<< SEARCH` / `====` / `>>>> REPLACE` and miss `old_string` because of indent or `\r\n`.

**Decision:**

1. Structured `<tool_call=edit_file : {json}>` (GBNF required keys).
2. If the snippet is missing: normalize newlines → trailing whitespace → indent (tabs vs spaces) → difflib window. Ambiguous matches refuse rather than patch the wrong site.
3. Truncated JSON or two failed `edit_file`s on the same path → grammar prefers **`write_file` with the complete file**. If `new_string` already looks like a whole module, the runner may apply it as a write.

We do not make SEARCH/REPLACE the primary path. JSON tool calls fail less often when GBNF is on; fuzzy matching covers the remaining indent mistakes.

### 7. Follow-ups carry the original task

**Problem:** The UI sent only the new sentence (“also add logging”). The sidecar started a new agent with no memory of the first request.

**Decision:** Electron still **displays** the short follow-up. The sidecar `goal` is composed as original request + last finish summary + follow-up. Thought/tool IDs include `run_id` so a second turn cannot overwrite the first turn’s stream. Nested epistemic events strip `body` so the threading catalog does not dump into chat.

### 8. Prompts are files; runner lines are headings

**Problem:** Hardcoded English strings in `agent.py` made policy uneditable without a Python change, and duplicated `agent.md`.

**Decision:** System prompts: [`prompts/*.md`](prompts/). Runner feedback: [`prompts/feedback.md`](prompts/feedback.md). `feedback("stress")` inside `_handle_run_tests_results` loads `# _handle_run_tests_results.stress`. Placeholders are `{{name}}`. Restart the sidecar after edits (`MANGO_PROMPTS_DIR` overrides the folder).

`agent.md` stays dense on purpose. A 12B coding model will not follow a long style guide; the numbered workflow plus GBNF is the contract.

## Data flow (one GUI turn)

1. User types in Mango. Renderer may wrap a follow-up around the original goal.
2. Sidecar `Orchestrator` builds an `Agent` with GUI flags (see table above).
3. **Context** assembles system prompt + goal + recent tool results + verification feedback under `max_prompt_chars` (48k in GUI).
4. **Runtime** generates thought, then a GBNF-constrained tool call.
5. **Tools** execute in the workspace (path sandbox). Plan-gate may reject writes.
6. **CodeIntel** refreshes on lookup / after edits; impact snippets go back into context.
7. **Verification path:** `compile()` then pytest. Optional `mango.verify.json` is a separate project-level loop (SWE-style), not the GUI pytest executor.
8. Finish: `summary.md` must say what changed, why, test result, and what a later follow-up should know.

## Modules

| Module | Path | Role |
|---|---|---|
| Runtime | [`runtime/`](runtime/) | GGUF load, `complete()`, grammar, KV cache |
| Context | [`context/`](context/) | Prompt assembly, verification feedback slot |
| CoT | [`cot/`](cot/) | Optional JSON “next tool” cycle |
| Tools | [`tools/`](tools/) | Parser (canonical + XML `name=`), GBNF, implementations, fuzzy `edit_file` |
| Epistemic | [`epistemic/`](epistemic/) | Sub-agent for signatures; compact module lookups |
| CodeIntel | [`codeintel/`](codeintel/) | SQLite index, `impact()`, file slicing |
| Verification | [`verification/`](verification/) | Optional command-based verify config |
| Agent | [`agent/`](agent/) | Loop, sidecar, benchmarks, SWE-bench harness |
| App | [`apps/electron/`](apps/electron/) | Desktop UI |

Deeper loop knobs and SWE-bench commands: [`agent/README.md`](agent/README.md). Prompt file list: [`prompts/README.md`](prompts/README.md). [`ARCHITECTURE.md`](ARCHITECTURE.md) is the original module sketch; this README is the current behavior.

## Quick start

Python 3.10+ (3.12 is typical). From the repo root:

```powershell
.\install.cmd
```

Then:

```powershell
cd apps\electron
npm install
npm run dev
```

Set the GGUF path in `runtime/config.yaml`. After changing agent, tools, or `prompts/`, restart the sidecar (not only the renderer).

Manual editable installs (same packages as `install.cmd`):

```powershell
pip install -e runtime/python -e tools/python -e context/python -e cot/python -e epistemic/python -e codeintel/python -e verification/python -e "agent/python[dev]" -e cli/python
```

After install, open a **new** terminal — `mango` runs the Textual CLI from any folder.

## Windows installer

Build a distributable NSIS installer (Electron + bundled Python sidecar):

```powershell
.\build.cmd
```

Artifacts land in `apps/electron/release/` (e.g. `Mango-Setup-0.1.0.exe`). Options:

- `.\build.cmd -SkipSidecar` — UI only (system Python)
- `.\build.cmd -Publish` — upload a GitHub Release to **mango-public** (`GH_TOKEN` required)
- `.\build.cmd -Version 0.2.0` — bump version before packaging

Installed builds check **Help → Check for Updates** against [mango-public releases](https://github.com/ToldByNun/mango-public/releases).

The installer ships a **portable embeddable Python** (not a machine-local `.venv`). Recipients set their GGUF path under **Settings** after install.

## Tests

CI runs the full unit suite on every push/PR (excludes `smoke` / `swebench_live`). Locally:

```powershell
pytest -q -m "not smoke and not swebench_live" agent/python/tests
pytest -q -m "not smoke and not swebench_live" tools/python/tests
pytest -q -m "not smoke and not swebench_live" runtime/python/tests
pytest -q -m "not smoke and not swebench_live" context/python/tests
pytest -q -m "not smoke and not swebench_live" cot/python/tests
pytest -q -m "not smoke and not swebench_live" epistemic/python/tests
pytest -q -m "not smoke and not swebench_live" codeintel/python/tests
pytest -q -m "not smoke and not swebench_live" verification/python/tests
pytest -q -m "not smoke and not swebench_live" cli/python/tests
pytest -q agent/python/mango_dataset/tests
```

Internal coding benchmark and official SWE-bench Lite: [`agent/README.md`](agent/README.md).
