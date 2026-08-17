# Runtime

Model Runner und GGUF-Loading — die einzige Inferenz-Instanz für alle Agenten-Kontexte.

**Sprache:** C++ (Kern), Python (Bindings)

## Geplante Komponenten

- `ModelRunner` — Inferenz, Sampling, Abort
- `GGUFLoader` — Modell laden/entladen, Metadaten

## Struktur

```
runtime/
├── cpp/          # Performance-kritischer Kern
└── python/       # Python-Bindings für Agent-Runtime
```
