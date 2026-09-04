# Agent Loop

Each turn: short thought → GBNF tool call → execute → (optional verify) → repeat.

GUI defaults: plan gate for third-party APIs (`declare_apis` → `ask_epistemic`), no CoT cycles, auto-pytest after Python mutations.

Roblox mode: `rbx_*` tools + `rbx_api` + `lookup_playbook`; no filesystem writes.

Knowledge: prefer [[../BRIEF|Brief]] → `rag_search` → this vault.

See [[Architecture]], [[Playbooks]].
