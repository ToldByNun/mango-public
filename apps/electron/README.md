# Electron App

Cursor-inspired **agent window**: sessions, live transcript, composer. Python sidecar talks JSONL.

```powershell
cd apps/electron
npm install
npm run dev
```

The main process starts `agent/python/.venv/Scripts/python.exe -m mango_agent.serve --config runtime/config.yaml`. Open a workspace, type a goal, watch thought / file edits / verify pills stream in.

## Layout

- 48px activity rail, 260px session list, transcript, floating composer, 22px status bar
- Tokens: `src/renderer/src/styles/tokens.css`

## Sidecar protocol

stdin/stdout JSON lines:

```json
{"id": "1", "method": "health", "params": {}}
{"id": "2", "method": "run", "params": {"session_id": "…", "goal": "…", "workspace": "…"}}
{"event": "agent.file", "session_id": "…", "payload": {"path": "a.py", "added": 3, "removed": 1}}
```
