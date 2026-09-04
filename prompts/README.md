# System prompts (SLM-optimized)

Edit these markdown files to change model instructions. Loaded at startup
(`MANGO_PROMPTS_DIR` overrides the folder). Restart the sidecar after edits.

XML-style tags (`<identity>`, `<protocol>`, …) help small models parse rules.
Critical deps path is redundant across agent + CoT + feedback.

| File | Used for |
|---|---|
| `agent_v2.md` | Default coding agent (`thinking=off`) |
| `agent_think.md` / `agent_deep.md` / `agent_max.md` | GUI thinking picker |
| `ask.md` / `plan.md` / `debug.md` / `refactor.md` | Slash modes |
| `roblox.md` | Roblox Studio mode |
| `epistemic.md` | Third-party API research sub-agent |
| `epistemic_codebase.md` | Local codebase research sub-agent |
| `cot.md` / `cot_chain_step.md` / `cot_chain_summarize.md` | Chain-of-thought |
| `summary.md` | Finish message after tests |
| `title.md` | Session title |
| `swebench.md` | SWE-bench issue fixing |
| `security_review.md` | Dataset / security-audit training |
| `feedback.md` | Runner replies after a tool turn |

## Deps lock (install + permission)

Runner **sole-forces** (GBNF — model cannot emit write/edit yet):

1. `declare_apis`
2. `ask_epistemic`
3. `install_packages` (only if imports missing; confirm popup — Deny unlocks write)
4. then `write_file`

Task-prompt install lock is auto-bound after declare (no extra turn).

Greenfield Discord/CLI bots skip lock/race design-review thrash after a successful write.

## Thinking level (GUI)

| Level | Prompt file | Thought tokens | CoT chain / cycles |
|---|---|---|---|
| `off` | `agent_v2.md` | 128 | 0 / 0 |
| `think` | `agent_think.md` | 256 | 2 / 3 |
| `deep` | `agent_deep.md` | 384 | 3 / 5 |
| `max` | `agent_max.md` | 512 | 3 / 6 |
