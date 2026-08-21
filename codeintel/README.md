# CodeIntel

Indexed codebase analysis so the agent does not rediscover the repo on every request.

**v1 choice:** Python `ast` (no extra dependency, accurate for this stack) + **SQLite** (incremental updates by file hash/mtime). Tree-sitter can be added later for multi-language support.

## What is stored

- file list (path, mtime, size, hash)
- symbols (functions, classes, methods) with signature and location
- references (calls / names)
- imports between files (resolved when possible)
- git snapshot (`git status --porcelain`, last 5 commits)

Index file: `{repo}/.mango/codeintel.sqlite`

`refresh()` is incremental: unchanged files are skipped.

## Query API

```python
from mango_codeintel import CodeIndex

index = CodeIndex("/path/to/repo")
index.refresh()
index.get_symbol_definition("greet")
index.get_references("greet")
index.get_relevant_files("Wo wird greet aufgerufen")
index.lookup("Wo wird Funktion greet aufgerufen?")
```

## Agent tool

```text
<tool_call=codebase_lookup : {"query": "Wo wird Funktion greet aufgerufen?"}>
```

Returns compact definition/reference hits with short snippets — not whole files.

`CodeIndex.slice_file(path)` / `slice_source(source)` produce prompt-safe slices: signature + 5 body lines. The agent stores these in deterministic memory instead of raw reads.

## Tests

```powershell
cd codeintel/python
pip install -e ".[dev]"
pytest -v
```
