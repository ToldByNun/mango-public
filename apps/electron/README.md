# Electron App

DevDeck Desktop-App — UI, Session-Management, IPC zur Agent-Runtime.

**Sprache:** TypeScript (Electron)

## Geplante Komponenten

- Main Process — Fenster, IPC, Python-Bridge
- Renderer — Session-UI, Logs, Tool-Ausgaben
- Preload — sichere IPC-Exposition

## Struktur

```
apps/electron/
└── src/
    ├── main/       # Electron Main Process
    ├── renderer/   # UI
    └── preload/    # Preload Scripts
```
