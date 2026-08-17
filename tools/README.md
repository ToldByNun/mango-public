# Tools

Tool Calling Parser und Tool-Implementierungen.

**Sprache:** Python (Kern), TypeScript (Desktop-Bridge)

## Geplante Komponenten

- `ToolRegistry` — register, list, get_schema
- `ToolParser` — parse, validate
- `ToolExecutor` — execute, cancel

## Struktur

```
tools/
├── python/       # Parser, Registry, Implementations
└── typescript/   # Electron / IPC Tool Bridge
```
