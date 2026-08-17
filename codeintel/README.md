# CodeIntel

Codebase Intelligence — Indexierung, semantische Suche, Snippet-Auswahl.

**Sprache:** Python

## Geplante Komponenten

- `CodeIndex` — index, refresh
- `CodeQuery` — symbols, references, relevant_files
- `SnippetProvider` — get_snippets

## Struktur

```
codeintel/
└── python/
    └── adapters/   # Sprach-agnostische Adapter (Tree-sitter, LSP)
```
