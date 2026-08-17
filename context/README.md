# Context

Prompt Window und Context Engine — Zusammenstellung des Prompt-Fensters unter Token-Budget pro Agenten-Kontext.

**Sprache:** C++ (Token-Budget), Python (Zusammenstellung)

## Geplante Komponenten

- `ContextEngine` — assemble, trim, inject
- `ContextProfile` — limits, priorities, templates
- `PromptWindow` — finales Prompt-Fenster für Runtime

## Struktur

```
context/
├── cpp/          # Token-Budget & Trimming
└── python/       # Kontext-Zusammenstellung & Profile
```
