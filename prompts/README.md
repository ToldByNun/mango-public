# System prompts

Edit these markdown files to change model instructions. The agent loads them at startup
(override directory with `MANGO_PROMPTS_DIR`).

| File | Used for |
|---|---|
| `agent_v2.md` | Default coding agent (`thinking=off`) |
| `agent_think.md` / `agent_deep.md` / `agent_max.md` | Full agent prompts for the GUI thinking picker (same protocol as `agent_v2`, stronger CoT) |
| `ask.md` / `plan.md` / `debug.md` / `refactor.md` | Slash modes |
| `epistemic.md` | Third-party API research sub-agent |
| `epistemic_codebase.md` | Local codebase research sub-agent |
| `cot.md` / `cot_chain_step.md` / `cot_chain_summarize.md` | Chain-of-thought |
| `summary.md` | Finish message after tests |
| `title.md` | Session title |
| `swebench.md` | SWE-bench issue fixing |
| `security_review.md` | Dataset / security-audit training prompts |
| `feedback.md` | Runner replies after a tool turn |

## Thinking level (GUI)

`thinking_preset` in `mango_agent.thinking` sets CoT cycles, thought token budget, and sanitize caps.
`compose_agent_system_prompt(level)` loads the matching full prompt file (not a short suffix).

| Level | Prompt file | Thought tokens | CoT chain / cycles |
|---|---|---|---|
| `off` | `agent_v2.md` | 128 | 0 / 0 |
| `think` | `agent_think.md` | 256 | 2 / 3 |
| `deep` | `agent_deep.md` | 384 | 4 / 6 |
| `max` | `agent_max.md` | 512 | 6 / 10 |
