# DevDeck

Lokales agentic coding framework: **ein lokales Modell, viele spezialisierte Agenten-Kontexte**.

DevDeck orchestriert lokale LLM-Inferenz (GGUF), Kontext-Management, Tool-Calling, epistemische Sub-Agenten und Codebase-Intelligence in einer einheitlichen Agent-Runtime — steuerbar über eine Electron-Oberfläche.

## Module

| Modul | Pfad | Sprache | Kurzbeschreibung |
|-------|------|---------|------------------|
| Runtime | [`/runtime`](runtime/) | C++ | Modell laden & inferieren |
| Context | [`/context`](context/) | C++ / Python | Prompt-Fenster & Kontext-Engine |
| CoT | [`/cot`](cot/) | Python | Chain-of-Thought Engine |
| Tools | [`/tools`](tools/) | Python / TypeScript | Tool-Parser & Implementierungen |
| Epistemic | [`/epistemic`](epistemic/) | Python | Epistemische Engine & Sub-Agenten |
| CodeIntel | [`/codeintel`](codeintel/) | Python | Codebase Intelligence |
| Verification | [`/verification`](verification/) | Python | Build / Test / Verify Loop |
| Agent | [`/agent`](agent/) | Python / TypeScript | Agent-Runtime & Orchestrator |
| App | [`/apps/electron`](apps/electron/) | TypeScript | Electron Desktop-App |

Ausführliche Architektur: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Projektstatus

**Phase 0 — Struktur.** Enthält Ordner, leere Module und Platzhalter. Keine Implementierungslogik.

## Sprachen

- **C++** — Performance-kritische Runtime (GGUF-Loading, Inferenz)
- **Python** — Agent-Logik, Orchestrierung, Code-Analyse
- **TypeScript** — Electron-UI und Tool-Bridge zur Desktop-Umgebung

## Schnellstart (geplant)

```bash
# Runtime bauen (C++)
cd runtime/cpp && mkdir build && cd build && cmake .. && cmake --build .

# Python-Umgebung
python -m venv .venv && source .venv/bin/activate  # bzw. .venv\Scripts\activate auf Windows
pip install -e .

# Electron-App
cd apps/electron && npm install && npm run dev
```
