# Architecture

Mango splits **UI**, **agent loop**, and **inference**.

- Electron (or Roblox Studio plugin) never talks to the GGUF directly.
- `python -m mango_agent.serve` is the JSONL sidecar.
- Tools mutate a jailed workspace (or Studio DataModel via host bridge).

See also [[Agent Loop]], [[Roblox Studio Plugin]], [[Playbooks]].
