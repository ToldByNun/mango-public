# Mango CLI

Terminal UI for Mango — same agent loop as the Electron app, structured closer to **Aider** / **Claude Code**.

## Setup

From the **repo root**:

```powershell
.\install.cmd
```

Then close all terminals and open a fresh one.

Manual:

```powershell
pip install -e .\cli\python
```

## Run

```powershell
cd C:\path\to\your\project
mango
```

With an initial goal:

```powershell
mango "Add a cyberpunk clock script with tests"
```

Options:

| Flag | Meaning |
|------|---------|
| `-w / --workspace` | Project folder (default: cwd) |
| `-c / --config` | YAML path (default: `<workspace>/.mango/config.yaml`) |

First run creates `.mango/config.yaml` (seeded from the Mango install when possible). Set `model.path` there.

## Slash commands

| Command | What it does |
|---------|----------------|
| `/help` | Commands + keys |
| `/ask …` | Read-only Q&A over the workspace |
| `/plan …` | Draft a plan (no file edits) |
| `/debug …` | Debug a failure |
| `/refactor …` | Focused rename / cleanup |
| `/clear` | Clear transcript |
| `/status` | Workspace / model / mode |
| `/quit` | Exit |

Each mode uses a distinct accent color in the prompt and transcript (same palette as the GUI).

## Keys

| Key | Action |
|-----|--------|
| `Enter` | Send / run goal |
| `Shift+Enter` | New line |
| `Esc` | Cancel running agent |
| `Ctrl+L` | Clear transcript |
| `Ctrl+C` | Cancel if running, else quit |

## Layout

```
mango · ~/project · ask · mango-1.0-Q2_K_L
╭ mango ────
  cwd     …
  hint    /help · /ask · /plan …
❯ /ask what command types exist?
  ● list_dir
  ● read_file
  ✓ done
  ── answer ──
· ready  /ask  completed · 4 iters    ⏎ send  ⇧⏎ newline  esc cancel  /help
```

## Notes

- GUI remains the primary surface; CLI is for terminal-only workflows.
- Same Orchestrator modes as the Electron sidecar (`ask`, `plan`, `debug`, `refactor`, agent).
- Restart the CLI after Python agent changes.
