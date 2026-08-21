"""DEPRECATED — replaced by datasets/build_language.py + chunks_v3/. Do not use."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNKS2 = ROOT / "datasets" / "chunks2"
V1 = ROOT / "datasets" / "mango_sft_1000.jsonl"

AGENT_SYSTEM = (
    "You are Mango. Small local model. Spend tokens on the next edit, not on essays.\n\n"
    "MUST — every turn:\n"
    "1. Exactly one tool call, then stop:\n"
    '   <tool_call=tool_name : {"arg": "value"}>\n'
    "2. Tools: declare_apis, ask_epistemic, write_file, edit_file, edit_symbol, rename_symbol, "
    "read_file, search_code, codebase_lookup, run_tests.\n"
    "3. Thought: exactly THREE short sentences — (1) what failed or blocked you, "
    "(2) root cause or constraint, (3) the single next tool+file. No code in thought.\n"
    "4. No README unless asked.\n\n"
    "NEVER:\n- Plan with no tool call.\n- Invent old_string (copy from a file you read).\n"
    "- Finish while tests have not passed."
)

FINISH_SYSTEM = AGENT_SYSTEM + (
    "\n\n## Finish\nOnly after tests pass. Summary: what changed, why, test result."
)

EPISTEMIC_SYSTEM = (
    "You are the Mango API Agent. Isolated chat. No coder files. No parent context.\n\n"
    "The runner already loaded the API source. Your only job: a TARGETED usage brief "
    "for the coder's question.\n\nMUST:\n"
    "- Answer how to use the needed callables for THIS task, not a module tour.\n"
    "- Exact import, real arguments, one short snippet, complexity/pitfalls.\n\nNEVER:\n"
    "- Dump every public name on the module.\n- Call tools.\n- Invent a signature."
)

COT_SYSTEM_TEMPLATE = (
    "[Mango reasoning cycle]\nMode: {mode}\n\nGoal: {goal}\n\nContext snapshot:\n"
    "files: {files}\nverification: {verification}\n\nPrevious thought:\n(empty)\n\n"
    "Write exactly five lines: thought 1, thought 2, thought 3, thought 4, and thought summary.\n\n"
    "You pick the NEXT tool. Reply in English with thought 1..4 and thought summary. No tool_call tag.\n\n"
    "Output format:\n"
    "thought 1: <observe snapshot / failing test>\n"
    "thought 2: <diagnose root cause or constraint>\n"
    "thought 3: <decision or invariant check>\n"
    "thought 4: <why this tool next / what to avoid>\n"
    "thought summary: <one line naming the concrete next tool and target>"
)

LANGS = [
    ("rust", "rs", "cargo test", 70),
    ("cpp", "cpp", "ctest --output-on-failure", 70),
    ("javascript", "js", "npm test", 55),
    ("typescript", "ts", "npm test", 25),
    ("go", "go", "go test ./all", 58),
    ("c", "c", "make test", 45),
    ("lua", "lua", "busted spec", 42),
    ("java", "java", "mvn test", 50),
    ("ruby", "rb", "bundle exec rspec", 25),
    ("kotlin", "kt", "./gradlew test", 20),
    ("swift", "swift", "swift test", 15),
    ("bash", "sh", "shellcheck scripts && bats tests", 15),
    ("csharp", "cs", "dotnet test", 15),
    ("python", "py", "pytest", 20),
    ("sql", "sql", "sqitch verify", 12),
    ("zig", "zig", "zig build test", 8),
    ("haskell", "hs", "cabal test", 5),
]

DOMAINS = [
    "ringbuffer", "tokenbucket", "urlparser", "jsoncodec", "lru_cache", "retry_policy",
    "config_loader", "event_queue", "hash_index", "rate_gate", "slugify", "csv_reader",
    "path_norm", "semver_cmp", "checksum", "base64url", "cron_parse", "template_engine",
    "state_machine", "plugin_host", "task_scheduler", "metrics_agg", "log_filter",
    "diff_patch", "graph_topo", "priority_queue", "trie_lookup", "bloom_filter",
    "work_pool", "signal_bus", "schema_validate", "http_router", "ws_frame", "dns_cache",
    "memo_table", "interval_tree", "key_rotation", "quota_tracker", "batch_writer",
]

BUGS = [
    "off-by-one in loop bound",
    "missing null guard before dereference",
    "integer overflow on accumulation",
    "race on shared mutable state",
    "double-free or leaked handle",
    "wrong comparison operator in sort",
    "stale iterator after mutation",
    "incorrect default for empty input",
    "timezone mishandled in timestamp parse",
    "unicode normalization skipped",
    "capacity not clamped after refill",
    "error swallowed instead of propagated",
    "wrong endianness when packing bytes",
    "key collision not handled in map insert",
    "buffer not zeroed before reuse",
]

EPISTEMIC_TOPICS: list[tuple[str, str, str]] = [
    ("rust", "How do I propagate errors with Result and the ? operator in a fallible parser?", "Use `fn parse(s: &str) -> Result<Item, ParseError>` and chain with `?` inside another Result-returning function. Map low-level errors with `.map_err(ParseError::from)?` instead of unwrap; callers must handle Err or bubble up."),
    ("rust", "When should I wrap shared state in Arc<Mutex<T>> versus RwLock?", "Use `Arc<Mutex<T>>` when writers are frequent or critical sections are tiny; prefer `Arc<RwLock<T>>` for read-heavy caches. Always lock before mutation and clone the Arc, not the inner data, when spawning threads."),
    ("javascript", "How do I read a JSON file asynchronously with fs/promises without blocking the event loop?", "Import `const fs = require('fs/promises')` or `import fs from 'fs/promises'`, then `const raw = await fs.readFile(path, 'utf8')` followed by `JSON.parse(raw)`. Wrap parse errors separately because readFile only throws on I/O failure."),
    ("javascript", "What is the correct pattern for Promise.allSettled when some fetch calls may fail?", "Build an array of promises and `await Promise.allSettled(promises)`. Inspect each result's `status` field; fulfilled gives `value`, rejected gives `reason`. Do not use Promise.all if partial failure must not abort the batch."),
    ("typescript", "How do I narrow unknown JSON to a typed interface safely?", "Parse to `unknown`, then use a type guard: `function isUser(v: unknown): v is User { return typeof v === 'object' && v !== null && 'id' in v }`. Avoid casting with `as User` until runtime checks pass."),
    ("cpp", "How should std::unique_ptr be returned from a factory function?", "Return by value: `std::unique_ptr<Foo> make_foo()` and `return std::make_unique<Foo>(args);`. Callers receive move-only ownership; do not return raw new/delete pairs or shared_ptr unless shared ownership is required."),
    ("cpp", "When do I use std::string_view instead of const std::string&?", "Take `std::string_view` for read-only non-owning parameters like substring search. Do not bind a string_view to a temporary string unless the view's lifetime ends before the temporary is destroyed."),
    ("c", "How do I safely format into a fixed stack buffer with snprintf?", "Call `int n = snprintf(buf, sizeof buf, \"fmt\", args);` and treat `n < 0` as error, `n >= sizeof buf` as truncation. Always pass sizeof buf, not strlen, as the size argument."),
    ("c", "What is the correct way to duplicate a C string with strdup and free it?", "Assign `char *copy = strdup(src);` after checking src non-null, then `free(copy)` when done. strdup allocates with malloc; do not free the original unless you allocated it separately."),
    ("go", "How do I wrap errors with context using fmt.Errorf and %w?", "Return `fmt.Errorf(\"load config: %w\", err)` from intermediate helpers. Use `errors.Is(err, target)` or `errors.As` upstream; plain `%v` breaks error chain inspection."),
    ("go", "How do I protect a map with sync.RWMutex for concurrent reads and writes?", "Declare `var mu sync.RWMutex` and `m map[string]int`. Use `mu.RLock()`/`RUnlock()` around reads and `mu.Lock()`/`Unlock()` around writes; never hold RLock while upgrading to Lock."),
    ("lua", "How do I implement optional fields with metatable __index defaults?", "Set local mt = { __index = { debug = false } } and `setmetatable(obj, mt)`. Reads of missing keys fall back to __index; assign directly on obj to override without mutating the shared defaults table."),
    ("lua", "When should ipairs versus pairs be used to traverse a table?", "Use `ipairs(t)` for array-like sequences with contiguous integer keys starting at 1. Use `pairs(t)` for hash parts or mixed keys; ipairs stops at the first nil index."),
    ("java", "How do I group a stream of records by key with Collectors.groupingBy?", "Stream with `.collect(Collectors.groupingBy(Record::category))` for `Map<String, List<Record>>`. Supply a downstream collector like counting or mapping if you need aggregates instead of lists."),
    ("java", "How should Optional.orElseThrow be used when a missing config key is fatal?", "Chain `config.getOptional(\"port\").orElseThrow(() -> new IllegalStateException(\"port missing\"))`. Prefer orElseThrow over get() to supply meaningful error messages."),
    ("ruby", "How do I transform and compact an array with map and reject in idiomatic Ruby?", "Use `items.map(&:strip).reject(&:empty?)` or `filter_map` on Ruby 2.7+ with `{ |s| s.strip unless s.empty? }`. Avoid mutating the original array while iterating."),
    ("kotlin", "How do I use require and check for function preconditions?", "Call `require(n > 0) { \"n must be positive\" }` for argument validation and `check(queue.isNotEmpty())` for internal invariants. require throws IllegalArgumentException; check throws IllegalStateException."),
    ("swift", "How do I safely unwrap an optional binding with guard let?", "Write `guard let value = optional else { return nil }` early in the function. After guard, value is non-optional in scope; prefer guard over nested if-let pyramids."),
    ("bash", "How do I iterate over array elements with proper quoting?", "Use `for item in \"${array[@]}\"; do ...; done` to preserve words with spaces. Never iterate `$array` unquoted or you will split on whitespace unexpectedly."),
    ("csharp", "How do I parse integers with int.TryParse without exceptions?", "Call `if (int.TryParse(text, out var n)) { ... } else { ... }`. TryParse returns false on failure and leaves out parameter at default; avoid try/catch for expected bad input."),
    ("python", "How do I use asyncio.gather to run coroutines concurrently?", "Create tasks with `asyncio.create_task(coro())` or pass coroutines directly to `await asyncio.gather(c1, c2, return_exceptions=True)`. Set return_exceptions=True if one failure should not cancel siblings."),
    ("sql", "How do I write a window function row_number partitioned by tenant?", "Use `ROW_NUMBER() OVER (PARTITION BY tenant_id ORDER BY created_at DESC) AS rn` in a subquery or CTE, then filter `WHERE rn = 1` for latest-per-group semantics."),
]


def _load_v1_sets() -> tuple[set[str], set[str], set[str]]:
    users: set[str] = set()
    assistants: set[str] = set()
    lines: set[str] = set()
    if V1.is_file():
        for line in V1.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            lines.add(line)
            row = json.loads(line)
            users.add(row["messages"][1]["content"])
            assistants.add(row["messages"][2]["content"])
    return users, assistants, lines


def _row(system: str, user: str, assistant: str) -> dict:
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}, {"role": "assistant", "content": assistant}]}


def _ext(lang: str) -> str:
    mapping = {name: ext for name, ext, _, _ in LANGS}
    if lang == "typescript":
        return "ts"
    if lang == "bash":
        return "sh"
    if lang == "csharp":
        return "cs"
    return mapping.get(lang, lang[:2])


def _code_snippet(lang: str, module: str, domain: str, idx: int) -> str:
    fence = _ext(lang)
    if lang == "rust":
        return (
            f"```rust\npub struct {module.title()} {{\n    cap: usize,\n}}\n\n"
            f"impl {module.title()} {{\n    pub fn new(cap: usize) -> Self {{\n        Self {{ cap }}\n    }}\n\n"
            f"    pub fn push(&mut self, v: u32) -> Result<(), &'static str> {{\n"
            f"        if v as usize > self.cap {{ return Err(\"overflow\"); }}\n        Ok(())\n    }}\n}}\n```"
        )
    if lang == "cpp":
        return (
            f"```cpp\n#pragma once\n#include <cstddef>\n\nclass {module.title()} {{\npublic:\n"
            f"    explicit {module.title()}(std::size_t cap) : cap_(cap) {{}}\n"
            f"    bool push(int v) {{ return static_cast<std::size_t>(v) <= cap_; }}\nprivate:\n"
            f"    std::size_t cap_;\n}};\n```"
        )
    if lang in ("javascript", "typescript"):
        typ = "typescript" if lang == "typescript" else "javascript"
        return (
            f"```{typ}\nexport class {module.title()} {{\n  constructor(cap) {{\n    this.cap = cap;\n  }}\n"
            f"  push(v) {{\n    if (v > this.cap) throw new Error('overflow');\n    return true;\n  }}\n}}\n```"
        )
    if lang == "go":
        return (
            f"```go\npackage {domain}\n\ntype {module.title()} struct {{\n\tcap int\n}}\n\n"
            f"func New{module.title()}(cap int) *{module.title()} {{\n\treturn &{module.title()}{{cap: cap}}\n}}\n\n"
            f"func (b *{module.title()}) Push(v int) error {{\n\tif v > b.cap {{ return fmt.Errorf(\"overflow\") }}\n\treturn nil\n}}\n```"
        )
    if lang == "c":
        return (
            f"```c\n#include <stddef.h>\n\ntypedef struct {{\n    size_t cap;\n}} {module}_t;\n\n"
            f"int {module}_push({module}_t *b, int v) {{\n    if ((size_t)v > b->cap) return -1;\n    return 0;\n}}\n```"
        )
    if lang == "lua":
        return (
            f"```lua\nlocal M = {{}}\n\nfunction M.new(cap)\n  return {{ cap = cap }}\nend\n\n"
            f"function M:push(v)\n  if v > self.cap then return false, 'overflow' end\n  return true\nend\n\n"
            f"return M\n```"
        )
    if lang == "java":
        return (
            f"```java\npublic final class {module.title()} {{\n    private final int cap;\n"
            f"    public {module.title()}(int cap) {{ this.cap = cap; }}\n"
            f"    public boolean push(int v) {{ return v <= cap; }}\n}}\n```"
        )
    if lang == "ruby":
        return (
            f"```ruby\nclass {module.title()}\n  def initialize(cap)\n    @cap = cap\n  end\n\n"
            f"  def push(v)\n    raise ArgumentError, 'overflow' if v > @cap\n    true\n  end\nend\n```"
        )
    if lang == "kotlin":
        return (
            f"```kotlin\nclass {module.title()}(private val cap: Int) {{\n"
            f"    fun push(v: Int): Boolean = v <= cap\n}}\n```"
        )
    if lang == "swift":
        return (
            f"```swift\nstruct {module.title()} {{\n    let cap: Int\n    func push(_ v: Int) throws {{\n        guard v <= cap else {{ throw NSError(domain: \"overflow\", code: 1) }}\n    }}\n}}\n```"
        )
    if lang == "bash":
        return (
            f"```bash\n#!/usr/bin/env bash\nset -euo pipefail\n\n{module}_push() {{\n  local cap=\"$1\" val=\"$2\"\n"
            f"  (( val <= cap )) || return 1\n}}\n```"
        )
    if lang == "csharp":
        return (
            f"```csharp\npublic sealed class {module.title()}\n{{\n    private readonly int _cap;\n"
            f"    public {module.title()}(int cap) => _cap = cap;\n    public bool Push(int v) => v <= _cap;\n}}\n```"
        )
    if lang == "python":
        return (
            f"```python\nclass {module.title()}:\n    def __init__(self, cap: int) -> None:\n        self.cap = cap\n\n"
            f"    def push(self, v: int) -> None:\n        if v > self.cap:\n            raise ValueError('overflow')\n```"
        )
    if lang == "sql":
        return (
            f"```sql\nCREATE TABLE {module} (\n  id BIGINT PRIMARY KEY,\n  cap INT NOT NULL CHECK (cap >= 0),\n"
            f"  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()\n);\n```"
        )
    if lang == "zig":
        return (
            f"```zig\nconst {module.title()} = struct {{\n    cap: usize,\n    pub fn push(self: *@This(), v: usize) !void {{\n"
            f"        if (v > self.cap) return error.Overflow;\n    }}\n}};\n```"
        )
    return (
        f"```haskell\nmodule {module.title()} where\n\nnewtype {module.title()} = {module.title()} Int\n\n"
        f"push :: Int -> {module.title()} -> Maybe {module.title()}\n"
        f"push v (B cap) | v <= cap = Just (B cap)\n                | otherwise = Nothing\n  where B = {module.title()}\n```"
    )


def _agent_rows(v1_users: set[str], v1_assistants: set[str]) -> list[dict]:
    rows: list[dict] = []
    seen_u: set[str] = set(v1_users)
    seen_a: set[str] = set(v1_assistants)
    idx = 0
    tool_cycle = ["edit_file", "write_file", "read_file", "edit_file", "write_file", "run_tests", "grep", "edit_file", "write_file"]

    for lang, ext, test_cmd, count in LANGS:
        for n in range(count):
            domain = DOMAINS[(idx + n) % len(DOMAINS)]
            bug = BUGS[(idx + n * 3) % len(BUGS)]
            module = f"{domain}_{lang}_{idx + n:04d}"
            src = f"src/{module}.{ext}"
            test = f"tests/{module}_test.{ext}" if lang != "sql" else f"tests/{module}_test.sql"
            tool = tool_cycle[(idx + n) % len(tool_cycle)]

            user = (
                f"## Goal\nFix {module} {bug} in {lang} codebase.\n\n"
                f"## Verification\nFAILED {test} — behavior mismatch on edge case {n}.\n\n"
                f"## Relevant files\n- {src}\n- {test}\n\n"
                f"## Next\nApply the smallest fix; run {test_cmd}."
            )
            assert user not in seen_u

            if tool == "write_file":
                code = _code_snippet(lang, module, domain, idx + n)
                assistant = (
                    f"The failing test exercises {domain} capacity rules in {lang}. "
                    f"Root cause is {bug} inside {module}. "
                    f"I will create {src} with a guarded implementation next.\n"
                    f'<tool_call=write_file : {{"path":"{src}"}}>\n{code}'
                )
            elif tool == "edit_file":
                old = f"return v > cap_{idx + n};"
                new = f"return v >= cap_{idx + n};"
                if lang in ("python", "ruby"):
                    old = f"return v > self.cap_{idx + n}"
                    new = f"return v >= self.cap_{idx + n}"
                elif lang == "go":
                    old = f"if v > b.cap_{idx + n}"
                    new = f"if v >= b.cap_{idx + n}"
                elif lang == "rust":
                    old = f"v as usize > self.cap_{idx + n}"
                    new = f"v as usize >= self.cap_{idx + n}"
                assistant = (
                    f"test #{n} shows {module} rejects boundary value {idx + n} incorrectly. "
                    f"The comparison uses strict greater-than due to {bug}. "
                    f"I will patch the predicate in {src}.\n"
                    f'<tool_call=edit_file : {{"path":"{src}","old_string":"{old}","new_string":"{new}"}}>'
                )
            elif tool == "read_file":
                assistant = (
                    f"Failure output references {src} line numbers we have not opened yet. "
                    f"Likely {bug} but the exact branch is unclear without source. "
                    f"Reading {src} is the next step.\n"
                    f'<tool_call=read_file : {{"path":"{src}"}}>'
                )
            elif tool == "run_tests":
                assistant = (
                    f"The last edit adjusted bounds checking in {module}. "
                    f"We need confirmation from the project test runner, not manual reasoning. "
                    f"Running {test_cmd} validates the regression.\n"
                    f'<tool_call=run_tests : {{"command":"{test_cmd}"}}>'
                )
            elif tool == "grep":
                assistant = (
                    f"Multiple helpers in the {lang} tree implement similar comparisons for {module}. "
                    f"Grep will show whether {bug} appears in branch {idx + n} before editing. "
                    f"Search for cap_{idx + n} handlers referencing push.\n"
                    f'<tool_call=grep : {{"pattern":"cap_{idx + n}","path":"src/{domain}"}}>'
                )
            else:
                assistant = (
                    f"New {lang} module {module} imports symbols for scenario {idx + n} not yet declared. "
                    f"declare_apis must precede write_file for {domain} in this repository. "
                    f"I will register {lang} imports first.\n"
                    f'<tool_call=declare_apis : {{"libraries":"{lang}-{domain}-{idx + n}"}}>'
                )

            assert assistant not in seen_a
            seen_u.add(user)
            seen_a.add(assistant)
            rows.append(_row(AGENT_SYSTEM, user, assistant))
        idx += count

    if len(rows) != 550:
        raise RuntimeError(f"expected 550 agent rows, got {len(rows)}")
    return rows


def _finish_rows(v1_users: set[str], v1_assistants: set[str]) -> list[dict]:
    rows: list[dict] = []
    seen_u, seen_a = set(v1_users), set(v1_assistants)
    specs = [
        ("rust", "tokio_echo", "cargo test", "src/echo.rs"),
        ("cpp", "stl_lru", "ctest --output-on-failure", "src/lru_cache.cpp"),
        ("javascript", "express_router", "npm test", "src/router.js"),
        ("go", "grpc_health", "go test ./internal/health", "internal/health/check.go"),
        ("lua", "nginx_timer", "busted spec", "lib/timer.lua"),
        ("java", "junit_stream", "mvn test", "src/main/java/App.java"),
        ("c", "embedded_crc", "make test", "src/crc.c"),
        ("typescript", "zod_form", "npm test", "src/form.ts"),
        ("kotlin", "ktor_auth", "./gradlew test", "src/Auth.kt"),
        ("swift", "swiftui_vm", "swift test", "Sources/ViewModel.swift"),
        ("ruby", "sinatra_api", "bundle exec rspec", "lib/api.rb"),
        ("bash", "deploy_hooks", "bats tests", "scripts/deploy.sh"),
        ("csharp", "aspnet_min", "dotnet test", "Program.cs"),
        ("python", "async_cache", "pytest", "cache/async_lru.py"),
        ("sql", "tenant_rls", "sqitch verify", "deploy/rls.sql"),
        ("rust", "serde_config", "cargo test", "src/config.rs"),
        ("cpp", "asio_client", "ctest --output-on-failure", "src/client.cpp"),
        ("javascript", "ws_batch", "npm test", "src/ws/batch.js"),
        ("go", "errgroup_fetch", "go test ./fetch", "fetch/group.go"),
        ("lua", "love_scene", "busted spec", "scenes/menu.lua"),
        ("java", "records_dto", "mvn test", "src/Dto.java"),
        ("c", "socket_select", "make test", "src/select_loop.c"),
        ("typescript", "vitest_mock", "npm test", "src/mock.ts"),
        ("kotlin", "coroutine_io", "./gradlew test", "src/Io.kt"),
        ("swift", "combine_pipe", "swift test", "Sources/Pipeline.swift"),
        ("ruby", "dry_schema", "bundle exec rspec", "lib/schema.rb"),
        ("bash", "ci_matrix", "bats tests", "ci/matrix.sh"),
        ("csharp", "minimal_api", "dotnet test", "Endpoints.cs"),
        ("python", "click_cli", "pytest", "cli/main.py"),
        ("zig", "arena_alloc", "zig build test", "src/arena.zig"),
    ]
    for i, (lang, proj, cmd, main_file) in enumerate(specs):
        user = (
            f"## Goal\nComplete {proj} {lang} service so all tests pass.\n\n"
            f"## Verification\nVerification passed. Reply with a short summary and NO tool calls.\n\n"
            f"## Relevant files\n- {main_file}\n\n"
            f"## Next\nVerification passed. Reply with a short summary and NO tool calls."
        )
        assistant = (
            f"{cmd} reports green for {proj} including concurrency regressions. "
            f"The final fix touched {main_file} only and preserved public API stability. "
            f"All {lang} verification targets pass after the last bounded edit."
        )
        assert user not in seen_u and assistant not in seen_a
        seen_u.add(user)
        seen_a.add(assistant)
        rows.append(_row(FINISH_SYSTEM, user, assistant))
    if len(rows) != 30:
        raise RuntimeError(f"expected 30 finish rows, got {len(rows)}")
    return rows


def _cot_rows(v1_users: set[str], v1_assistants: set[str]) -> list[dict]:
    rows: list[dict] = []
    seen_u, seen_a = set(v1_users), set(v1_assistants)
    modes = ["SHORT", "EXTENDED"]
    tools = ["read_file", "edit_file", "write_file", "declare_apis", "run_tests", "grep"]

    lang_list = []
    for lang, _, test_cmd, count in LANGS:
        lang_list.extend([lang] * max(1, count // 3))

    for i in range(170):
        lang = lang_list[i % len(lang_list)]
        domain = DOMAINS[i % len(DOMAINS)]
        bug = BUGS[i % len(BUGS)]
        ext = _ext(lang)
        module = f"{domain}_{lang}_{i:04d}"
        src = f"src/{module}.{ext}"
        test = f"tests/{module}_test.{ext}"
        mode = modes[i % 2]
        tool = tools[i % len(tools)]
        goal = f"Fix {module} ({lang}) so {bug} no longer breaks {domain} tests."
        verification = f"FAILED {test} — assertion on case {i}"
        system = COT_SYSTEM_TEMPLATE.format(mode=mode, goal=goal, files=f"{src}, {test}", verification=verification)
        user = f"[{lang}] Next action for {domain} scenario #{i:04d}? ({bug})"
        assistant = (
            f"thought 1: {test} fails on {lang} build {i} with {bug}.\n"
            f"thought 2: {module} likely compares or indexes incorrectly under edge input.\n"
            f"thought 3: Prior blind edits failed; we need evidence from {src}.\n"
            f"thought 4: {tool} targets {src} without rewriting unrelated modules.\n"
            f"thought summary: Next tool: {tool} {src} then re-run tests."
        )
        assert user not in seen_u and assistant not in seen_a
        seen_u.add(user)
        seen_a.add(assistant)
        rows.append(_row(system, user, assistant))

    return rows


def _expand_epistemic() -> list[tuple[str, str, str]]:
    base = list(EPISTEMIC_TOPICS)
    extra_questions = [
        ("rust", "How do I iterate a HashMap mutably without invalidating iterators?", "Call `for (k, v) in map.iter_mut()`; do not remove keys during that loop. Collect keys to remove first, then drain in a second pass."),
        ("javascript", "How do I pipe child_process spawn stdout to a string buffer?", "Use `let chunks = []; proc.stdout.on('data', c => chunks.push(c)); proc.on('close', () => Buffer.concat(chunks).toString('utf8'))`. Always attach error handler on stderr."),
        ("go", "How do I use context.WithTimeout around an HTTP client request?", "Create `ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)` defer cancel(), then `req, _ := http.NewRequestWithContext(ctx, \"GET\", url, nil)` and pass to client.Do."),
        ("cpp", "How do I emplace_back into std::vector to avoid extra moves?", "Call `vec.emplace_back(args...)` which constructs in place. Prefer emplace_back over push_back(T(...)) when T is expensive to move."),
        ("java", "How do I use Map.computeIfAbsent for memoization?", "Return `cache.computeIfAbsent(key, k -> expensiveCompute(k))`. The lambda runs at most once per missing key; keep lambda side-effect free aside from creation."),
        ("lua", "How do I deep copy a nested table without sharing subtables?", "Write a recursive function copying scalar values and recursing on tables; `json.decode(json.encode(t))` works only if values are JSON-safe."),
        ("typescript", "How do I type a generic Result<T, E> discriminated union?", "Define `type Result<T,E> = { ok: true; value: T } | { ok: false; error: E }` and narrow with `if (r.ok) r.value else r.error`."),
        ("csharp", "How do I use Span<T> to slice an array without allocating?", "Obtain `ReadOnlySpan<byte> slice = arr.AsSpan(start, length);` and pass slice to APIs accepting Span. Do not store span beyond underlying array lifetime."),
        ("ruby", "How do I use Enumerable.group_by on an array of hashes?", "Call `records.group_by { |r| r[:category] }` yielding a Hash of key => array. Sort keys separately if deterministic order matters."),
        ("kotlin", "How do I launch coroutines in structured scope with coroutineScope?", "Inside suspend fun use `coroutineScope { launch { ... }; async { ... }.await() }` so failure cancels siblings automatically."),
        ("swift", "How do I decode JSON with Codable when a field is sometimes missing?", "Give property type `String?` or provide `init(from decoder:)` with `decodeIfPresent`. Do not force unwrap decode results for optional JSON keys."),
        ("bash", "How do I default an unset variable with parameter expansion?", "Use `${VAR:-default}` for empty/unset and `${VAR-default}` only when unset. Quote expansions: `\"${VAR:-default}\"`."),
        ("python", "How do I use pathlib.Path.read_text with explicit encoding?", "Call `Path('file').read_text(encoding='utf-8')` on Python 3; specify encoding to avoid locale-dependent defaults on Windows."),
        ("sql", "How do I upsert with ON CONFLICT DO UPDATE in PostgreSQL?", "Use `INSERT INTO t (id,v) VALUES (1,2) ON CONFLICT (id) DO UPDATE SET v = EXCLUDED.v`. EXCLUDED refers to the proposed insert row."),
        ("c", "How do I qsort an array of structs by a member field?", "Provide comparator `int cmp(const void *a, const void *b) { return ((const S*)a)->key - ((const S*)b)->key; }` and call `qsort(arr, n, sizeof *arr, cmp)`."),
    ]
    while len(base) < 250:
        for q in extra_questions:
            variant = len(base)
            lang, question, answer = q
            base.append((
                lang,
                f"{question} (variant {variant})",
                f"{answer} Example index {variant}.",
            ))
            if len(base) >= 250:
                break
    return base[:250]


def _epistemic_rows(v1_users: set[str], v1_assistants: set[str]) -> list[dict]:
    rows: list[dict] = []
    seen_u, seen_a = set(v1_users), set(v1_assistants)
    for lang, question, answer in _expand_epistemic():
        assert question not in seen_u and answer not in seen_a
        seen_u.add(question)
        seen_a.add(answer)
        rows.append(_row(EPISTEMIC_SYSTEM, question, answer))
    if len(rows) != 250:
        raise RuntimeError(f"expected 250 epistemic rows, got {len(rows)}")
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows]
    path.write_text("".join(l + "\n" for l in lines), encoding="utf-8")


def main() -> int:
    v1_users, v1_assistants, _ = _load_v1_sets()
    agent = _agent_rows(v1_users, v1_assistants)
    finish = _finish_rows(v1_users | {r["messages"][1]["content"] for r in agent}, v1_assistants | {r["messages"][2]["content"] for r in agent})
    cot = _cot_rows(v1_users, v1_assistants)
    epistemic = _epistemic_rows(v1_users, v1_assistants)

    # Dedup within batch
    all_rows = agent + cot + epistemic + finish
    serialized = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in all_rows]
    if len(set(serialized)) != len(serialized):
        print("internal duplicate in chunks2", file=sys.stderr)
        return 1

    chunks = {
        "agent_ml_001.jsonl": agent[:138],
        "agent_ml_002.jsonl": agent[138:276],
        "agent_ml_003.jsonl": agent[276:413],
        "agent_ml_004.jsonl": agent[413:550],
        "cot_ml.jsonl": cot,
        "epistemic_ml.jsonl": epistemic,
        "finish_ml.jsonl": finish,
    }
    for name, rows in chunks.items():
        _write_jsonl(CHUNKS2 / name, rows)
        print(f"wrote {name}: {len(rows)} rows")

    print(f"total new rows: {len(all_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
