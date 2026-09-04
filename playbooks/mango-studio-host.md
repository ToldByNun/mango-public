---
name: mango-studio-host
triggers: roblox, studio, mango host, sidecar, plugin, 17880
---

# Start Mango Roblox Studio host + plugin

## When
User wants the Mango agent inside Roblox Studio, or host shows offline.

## Steps
1. Run `apps/roblox-studio/MangoStudio.cmd` (installs plugin as `.lua` + starts host).
2. Fully quit and reopen Roblox Studio if the plugin was just installed.
3. Open the **Mango** toolbar button; status should show online on `127.0.0.1:17880`.
4. Accept HTTP permission for localhost if prompted.
5. Pick a GGUF via the model chip if needed, then send a goal.

## Notes
- Studio loads `MangoPlugin.lua` only — not `.luau`.
- Plugin cannot spawn the EXE; host must already be running.
