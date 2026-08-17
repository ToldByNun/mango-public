# DevDeck — Architektur

## Leitprinzip

> **Ein lokales Modell, viele spezialisierte Agenten-Kontexte.**

DevDeck teilt eine einzige lokale LLM-Instanz (GGUF) zwischen mehreren spezialisierten Agenten-Kontexten. Jeder Kontext definiert eigene System-Prompts, erlaubte Tools, epistemische Regeln und Verifikations-Schleifen — ohne separate Modell-Instanzen pro Agent.

```
┌─────────────────────────────────────────────────────────────────┐
│                     Electron App (TypeScript)                    │
│              UI · Session · Tool-Bridge · IPC                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                   Agent Runtime / Orchestrator                   │
│         Routing · Session-State · Sub-Agent-Spawning             │
└─┬──────┬──────┬──────┬──────┬──────┬──────┬─────────────────────┘
  │      │      │      │      │      │      │
  ▼      ▼      ▼      ▼      ▼      ▼      ▼
Context  CoT  Tools Epist. Code  Verify Runtime
Engine       Parser Engine Intel  Loop   (GGUF)
```

## Datenfluss (Konzept)

1. **Agent** empfängt eine Aufgabe und wählt den passenden Agenten-Kontext.
2. **Context** baut das Prompt-Fenster aus System-Prompt, Verlauf, Code-Snippets und Tool-Schemas.
3. **Runtime** führt Inferenz auf dem lokalen GGUF-Modell aus.
4. **CoT** strukturiert Zwischenschritte (Plan → Act → Reflect) und steuert Iterationen.
5. **Tools** parst Modell-Ausgaben, führt Aktionen aus und liefert Ergebnisse zurück in den Kontext.
6. **Epistemic** bewertet Unsicherheit, aktiviert Sub-Agenten und eskaliert bei Wissenslücken.
7. **CodeIntel** liefert semantische Codebase-Kontexte (Symbole, Referenzen, Diff-Hints).
8. **Verification** schließt den Loop mit Build-, Test- und Lint-Checks ab.
9. Ergebnis fließt zurück an **Agent** → UI.

---

## Module

### `/runtime` — Model Runner & GGUF Loading

**Sprache:** C++ (Kern), Python (Bindings)

**Verantwortung:**
- Laden und Verwalten von GGUF-Modellen
- Tokenisierung, Batch-Inferenz, Sampling-Parameter
- Hardware-Abstraktion (CPU / GPU / quantisierte Varianten)
- Einzige Inferenz-Instanz für alle Agenten-Kontexte (Queue / Scheduling)

**Schnittstellen (geplant):**
- `ModelRunner` — infer, embed, abort
- `GGUFLoader` — load, unload, metadata

---

### `/context` — Prompt Window / Context Engine

**Sprache:** C++ (Token-Budget), Python (Zusammenstellung)

**Verantwortung:**
- Prompt-Fenster unter festem Token-Budget zusammenstellen
- Priorisierung: System-Prompt → aktuelle Aufgabe → Tool-Ergebnisse → Verlauf → Code-Kontext
- Kontext-Profile pro Agenten-Typ (Coder, Reviewer, Planner, …)
- Sliding-Window, Summarization-Hooks, Cache für wiederkehrende Prefixe

**Schnittstellen (geplant):**
- `ContextEngine` — assemble, trim, inject
- `ContextProfile` — limits, priorities, templates

---

### `/cot` — Chain-of-Thought Engine

**Sprache:** Python

**Verantwortung:**
- Strukturierte Reasoning-Schritte: Plan → Decompose → Execute → Reflect
- Iterations- und Abbruchkriterien (max steps, confidence threshold)
- Parsing und Validierung von CoT-Ausgaben des Modells
- Brücke zwischen roher Modell-Antwort und Tool-/Agent-Aktionen

**Schnittstellen (geplant):**
- `CoTEngine` — run_step, parse, should_continue
- `ThoughtTrace` — steps, metadata

---

### `/tools` — Tool Calling Parser & Implementations

**Sprache:** Python (Kern), TypeScript (Desktop-Bridge)

**Verantwortung:**
- Schema-definierte Tools (read_file, edit, shell, search, …)
- Parser für Modell-generierte Tool-Calls (JSON, XML, function-call-Format)
- Ausführung, Timeout, Fehler-Rückgabe an Context
- Registrierung tool-spezifischer Berechtigungen pro Agenten-Kontext

**Schnittstellen (geplant):**
- `ToolRegistry` — register, list, get_schema
- `ToolParser` — parse, validate
- `ToolExecutor` — execute, cancel

---

### `/epistemic` — Epistemic Engine & Sub-Agents

**Sprache:** Python

**Verantwortung:**
- Bewertung von epistemischer Sicherheit (bekannt / unsicher / spekulativ)
- Spawn spezialisierter Sub-Agenten bei Wissenslücken (Research, Verify, Clarify)
- Konfliktauflösung zwischen Sub-Agent-Ergebnissen
- Confidence-Scoring für Orchestrator-Entscheidungen

**Schnittstellen (geplant):**
- `EpistemicEngine` — assess, escalate
- `SubAgent` — spawn, merge_result
- `ConfidenceScore` — value, rationale

---

### `/codeintel` — Codebase Intelligence

**Sprache:** Python

**Verantwortung:**
- Indexierung: Symbole, Imports, Referenzen, Dateistruktur
- Semantische Suche und relevante Snippet-Auswahl für Context
- Diff-Awareness, Git-Integration (Status, Blame-Hints)
- Sprach-agnostische Adapter (Tree-sitter / LSP-Hooks geplant)

**Schnittstellen (geplant):**
- `CodeIndex` — index, refresh
- `CodeQuery` — symbols, references, relevant_files
- `SnippetProvider` — get_snippets

---

### `/verification` — Build / Test / Verify Loop

**Sprache:** Python

**Verantwortung:**
- Automatisierte Verifikation nach Agent-Aktionen
- Build-, Test-, Lint- und Type-Check-Runner
- Feedback-Schleife: Fehler → strukturierter Kontext → erneute Agent-Iteration
- Projekt-Profile (npm, cargo, cmake, pytest, …)

**Schnittstellen (geplant):**
- `VerificationLoop` — run, parse_output
- `Verifier` — build, test, lint
- `VerificationResult` — success, errors, artifacts

---

### `/agent` — Agent Runtime / Orchestrator

**Sprache:** Python (Kern), TypeScript (IPC-Adapter)

**Verantwortung:**
- Zentrale Orchestrierung aller Module
- Session- und Multi-Turn-State
- Routing zu spezialisierten Agenten-Kontexten
- Lifecycle: start → loop (context → infer → cot → tools → verify) → finish
- API für Electron-App und headless CLI

**Schnittstellen (geplant):**
- `AgentRuntime` — run, cancel, get_state
- `AgentContext` — profile, tools, epistemic_rules
- `Orchestrator` — route, spawn_sub_agent

---

### `/apps/electron` — Desktop App

**Sprache:** TypeScript (Electron)

**Verantwortung:**
- Benutzeroberfläche für Sessions, Logs, Tool-Ausgaben
- IPC zur Python-Agent-Runtime
- Native Desktop-Integration (Dateidialoge, Terminal-Bridge)
- Einstellungen: Modell-Pfad, Hardware, Agenten-Profile

---

## Agenten-Kontexte (Konzept)

Ein **Agenten-Kontext** ist kein separates Modell, sondern eine Konfiguration:

| Kontext | Fokus | Tools | Epistemic | Verification |
|---------|-------|-------|-----------|--------------|
| Coder | Implementierung | edit, read, shell | niedrig | build + test |
| Reviewer | Qualität | read, diff | hoch | lint |
| Planner | Architektur | read, search | mittel | — |
| Debugger | Fehlersuche | read, shell, test | hoch | test loop |
| Researcher | Recherche | search, read | sehr hoch | — |

Alle Kontexte teilen sich dieselbe **Runtime**-Instanz; **Context** wechselt Profile und Budgets.

---

## Abhängigkeiten zwischen Modulen

```
runtime  ←── agent, context, cot
context  ←── agent, codeintel, tools, verification
cot      ←── agent
tools    ←── agent, apps/electron
epistemic←── agent
codeintel←── agent, context
verification ←── agent, tools
agent    ←── apps/electron
```

Kein zirkulärer Import auf Modulebene geplant; gemeinsame Typen später in `/shared` oder via leichtes Protobuf/JSON-Schema.

---

## Nächste Schritte (Implementierung)

1. **Runtime:** GGUF-Loader + minimaler Inferenz-Loop (C++)
2. **Context:** Token-Budget + ein Context-Profile
3. **Agent:** Headless-Orchestrator ohne UI
4. **Tools:** read_file + edit als erste Tools
5. **Verification:** Ein Build-Runner (z. B. npm test)
6. **Electron:** Session-UI mit IPC-Stubs
