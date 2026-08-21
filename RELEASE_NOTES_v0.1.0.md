# Mango 0.1.0

First public Windows installer for **Mango** — local coding agent for small GGUF models.

## Install

1. Download **Mango-Setup-0.1.0.exe**
2. Install and open Mango
3. Open **Settings** and set your local `.gguf` model path
4. Open a workspace and start a session

## Included

- Desktop UI (Electron)
- Bundled portable Python sidecar (no system Python required)
- Auto-update via GitHub Releases (`latest.yml`)

## Notes

- Windows **x64** only
- Model weights are **not** included — use your own GGUF
- SmartScreen may warn on unsigned builds → More info → Run anyway

## Upload checklist (for this release)

Attach these three files from `apps/electron/release/` (same build):

- `Mango-Setup-0.1.0.exe`
- `Mango-Setup-0.1.0.exe.blockmap`
- `latest.yml`

Tag: `v0.1.0`
