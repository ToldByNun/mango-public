# Mango Roblox Studio Plugin

Local GGUF coding agent inside Roblox Studio. The Luau plugin is UI + DataModel bridge; inference runs in `mango-studio-host` → `mango_agent.serve`.

## Architecture

```
Studio Plugin (DockWidget)
    ↔ HTTP long-poll 127.0.0.1:17880
mango-studio-host
    ↔ JSONL stdin/stdout
mango_agent.serve (mode=roblox) + GGUF
```

Script edits use **`rbx_edit` only** (search/replace, unique match). No full-source overwrite. Deletes and bulk property sets require an explicit Allow/Deny dialog in the dock widget before mutation.

## Setup (Windows)

**One double-click:** [`MangoStudio.cmd`](MangoStudio.cmd) installs the local plugin and starts the host. Leave that window open while you use Mango in Studio.

From repo root you can also run `bin\mango-studio.cmd`.

### 1. Host

From the Mango repo (with your usual agent venv / PYTHONPATH):

```powershell
cd apps\roblox-studio\host\python
pip install -e .

# From repo root, with packages on PYTHONPATH (same as Electron sidecar):
$env:PYTHONPATH = "agent\python;tools\python;runtime\python;context\python;cot\python;epistemic\python;codeintel\python;verification\python;apps\roblox-studio\host\python"
python -m mango_studio_host --port 17880
```

Optional: wait until Studio is open:

```powershell
python -m mango_studio_host --wait-for-studio
```

Or use the helper scripts in this folder:

```powershell
..\..\..\..\apps\roblox-studio\Start-StudioHost.ps1
```

### 2. Plugin

```powershell
.\Install-StudioPlugin.ps1
```

Installs as **`MangoPlugin.lua`** (Studio does **not** load `.luau` from the Plugins folder). **Fully quit and reopen Studio**, then use the **Mango** toolbar button under the Plugins tab. Accept the HTTP permission prompt for `http://127.0.0.1:17880`.

Also enable **Game Settings → Security → Allow HTTP Requests** if prompted.

### 3. Model

Configure the same `runtime/config.yaml` / `~/.mango/runtime/config.yaml` GGUF path as the Electron app. First run loads the model via the sidecar.

## Usage

1. Start `mango-studio-host`.
2. Open a Place in Studio → Mango panel → status should show **Host: online**.
3. Type a goal (e.g. create a Script under ServerScriptService that prints Hello) → **Send**.
4. Destructive actions (`rbx_delete`, multi-instance `rbx_prop`) show **Allow / Deny** before applying.

## Tools (`mode=roblox`)

| Tool | Role |
|------|------|
| `rbx_tree` / `rbx_sel` / `rbx_read` | Orient / read |
| `rbx_edit` | Unique search/replace on Script source |
| `rbx_create` | New Instance (+ optional short seed source) |
| `rbx_prop` | Set property (bulk → confirm) |
| `rbx_delete` | Delete (always confirm) |

## Layout

```
apps/roblox-studio/
  MangoStudio.cmd            # install plugin + start host
  plugin/src/MangoPlugin.luau
  host/python/mango_studio_host/
  Install-StudioPlugin.cmd
  Start-StudioHost.cmd
  curated/roblox_api_cards.md
```
