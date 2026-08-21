# System prompts

Edit these markdown files to change model instructions. The agent loads them at startup (override directory with `MANGO_PROMPTS_DIR`).

| File | Used for |
|---|---|
| `agent.md` | GUI / default coding agent (`thinking=off` body) |
| `agent_think.md` / `agent_deep.md` / `agent_max.md` | Appended to `agent.md` for the GUI thinking picker |
| `swebench.md` | SWE-bench issue fixing |
| `epistemic.md` | API research sub-agent |
| `summary.md` | Finish message after tests (`{{goal}}`, `{{facts}}`) |
| `cot.md` | Chain-of-thought JSON cycle (`{{mode}}`, `{{schema}}`, …) |
| `cot_chain_step.md` / `cot_chain_summarize.md` | Verify-first CoT chain |
| `feedback.md` | Runner replies after a tool turn. Heading `# function` or `# function.variant` — `feedback("stress")` inside `_handle_run_tests_results` loads that block. |

Placeholders look like `{{name}}`. Keep these dense: the full text is injected into every model turn.

## Thinking level (GUI)

`thinking_preset` in `mango_agent.thinking` sets CoT cycles, thought token budget, and sanitize caps:

| Level | Thought tokens | CoT chain / cycles | Thought style |
|---|---|---|---|
| `off` | 128 | 0 / 0 | 1–2 sentences |
| `think` | 256 | 2 / 3 | 3–6 sentences |
| `deep` | 384 | 4 / 6 | short plan + diagnosis |
| `max` | 512 | 6 / 10 | verify-first chain; longer finish summary |

GUI still uses `plan_apis_first=True`, `max_tokens=4096`, `tool_max_tokens=2048`. `declare_apis` → `ask_epistemic` is required only for **third-party** libraries (pandas, numpy, …). Stdlib (`argparse`, `csv`, `pathlib`, `json`, …) may `write_file` immediately. The epistemic sub-agent is a nested Agent with its own prompt. SWE-bench does not use the plan gate (`write_file` is disabled there). Compile-check is `compile(..., "exec")` — parse only, no execution.
