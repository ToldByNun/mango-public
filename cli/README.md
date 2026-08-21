# Mango CLI

Textual terminal UI for Mango — same agent loop as the Electron app, mango-orange theme.

## Setup

From the **repo root**:

```powershell
.\install.cmd
```

Then **close all terminals** (including Cursor) and open a fresh one.

Manual install:

```powershell
pip install -e ..\..\cli\python
python -m mango_cli.path_setup
```

## Run

```powershell
cd C:\path\to\your\project
mango
```

First run creates `<project>/.mango/config.yaml` (seeded from the Mango install config when possible). Edit `model.path` there if needed.

Options:

- `-w / --workspace` — project folder (default: cwd)
- `-c / --config` — explicit YAML path

With an initial goal:

```powershell
mango "Add a cyberpunk clock script with tests"
```

Options:

- `-w / --workspace` — project folder (default: cwd)
- `-c / --config` — path to `runtime/config.yaml`

## Keys

| Key | Action |
|-----|--------|
| Ctrl+Enter | Run goal / follow-up |
| Esc | Cancel running agent |
| Ctrl+Q | Quit (Textual default) |

## Notes

- GUI remains the primary surface; CLI is for terminal-only workflows.
- Uses the same Orchestrator flags as the Electron sidecar (`plan_apis_first`, verification, runtime smoke).
- Restart the CLI after Python agent changes.
