# Agent

Agent Runtime und Orchestrator — zentrale Steuerung aller Module.

**Sprache:** Python (Kern), TypeScript (IPC-Adapter)

## Geplante Komponenten

- `AgentRuntime` — run, cancel, get_state
- `AgentContext` — profile, tools, epistemic_rules
- `Orchestrator` — route, spawn_sub_agent

## Struktur

```
agent/
├── python/       # Agent-Runtime & Orchestrator
└── typescript/   # IPC-Adapter für Electron
```
