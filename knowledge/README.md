# Knowledge layers

Three speeds for project context. Prefer the cheapest layer that answers the question.

| Tier | Speed | Source | Tool |
|------|-------|--------|------|
| **1 · Brief** | Instant | [`BRIEF.md`](BRIEF.md) | `project_brief` |
| **2 · RAG** | Medium | Indexed chunks (vault + playbooks + curated) in `.mango/knowledge.sqlite` | `rag_search` |
| **3 · Vault** | Slowest / clearest | Markdown notes with `[[wikilinks]]` | `vault_open` |

## When to use which

1. **Orientation / “what is this repo?”** → `project_brief`
2. **“Where do we handle X?” / fuzzy recall** → `rag_search`
3. **Full procedure or linked explanation** → `vault_open` (follow `[[links]]`)

Procedural “when X, do Y” runbooks still live in [`../playbooks/`](../playbooks/) and `lookup_playbook`.

## Vault conventions

- One topic per file under `vault/`
- Link with Obsidian-style `[[Note Title]]` or `[[note-file]]`
- Keep BRIEF.md to **one headline + one short paragraph** (≤ ~500 chars)
