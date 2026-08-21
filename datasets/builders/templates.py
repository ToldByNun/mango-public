from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BugTemplate:
    bug_class: str
    cwe: str
    description: str
    lang: str
    file_ext: str

    def vuln_old(self, mod: str, idx: int) -> str:
        return _VULN_OLD[self.lang][self.bug_class](mod, idx)

    def vuln_new(self, mod: str, idx: int) -> str:
        return _VULN_NEW[self.lang][self.bug_class](mod, idx)

    def wrong_fix(self, mod: str, idx: int) -> str | None:
        fn = _WRONG_FIX.get(self.lang, {}).get(self.bug_class)
        return fn(mod, idx) if fn else None

    def multi_old(self, mod: str, idx: int) -> str:
        return _MULTI_OLD.get(self.lang, {}).get(self.bug_class, lambda m, i: f"return handle_{m}_{i}()")(mod, idx)

    def multi_new(self, mod: str, idx: int) -> str:
        return _MULTI_NEW.get(self.lang, {}).get(self.bug_class, lambda m, i: f"return handle_{m}_{i}_v2()")(mod, idx)


# ---- Python ----
_PY_OLD = {
    "sqli": lambda m, i: f'cursor.execute(f"SELECT * FROM {m} WHERE id = \'{{{m}_id_{i}}}\'")',
    "pickle": lambda m, i: f"pickle.loads({m}_data_{i})",
    "path_traversal": lambda m, i: f"open(os.path.join(BASE_{m}, user_path_{i}))",
    "eval_exec": lambda m, i: f"eval({m}_expr_{i})",
    "race_thread": lambda m, i: f"self.{m}_count_{i} += 1",
    "asyncio_lock": lambda m, i: f"self.{m}_items_{i}.append(x)",
    "except_pass": lambda m, i: f"except Exception:  # {m}_{i}\n        pass",
}
_PY_NEW = {
    "sqli": lambda m, i: f'cursor.execute("SELECT * FROM {m} WHERE id = ?", ({m}_id_{i},))',
    "pickle": lambda m, i: f"json.loads({m}_data_{i}.decode())",
    "path_traversal": lambda m, i: f"open(safe_resolve(BASE_{m}, user_path_{i}))",
    "eval_exec": lambda m, i: f"ast.literal_eval({m}_expr_{i})",
    "race_thread": lambda m, i: f"with self._{m}_lock_{i}:\n            self.{m}_count_{i} += 1",
    "asyncio_lock": lambda m, i: f"async with self._{m}_lock_{i}:\n            self.{m}_items_{i}.append(x)",
    "except_pass": lambda m, i: f"except Exception as exc_{m}_{i}:\n        logger.error(exc_{m}_{i})\n        raise",
}
_PY_WRONG = {
    "race_thread": lambda m, i: f"threading.Lock()  # global, not per-{m}_{i}\n        self.{m}_count_{i} += 1",
}

# ---- JavaScript ----
_JS_OLD = {
    "prototype_pollution": lambda m, i: f"Object.assign({{}}, {m}Input_{i})",
    "innerHTML": lambda m, i: f"{m}El_{i}.innerHTML = {m}Html_{i}",
    "missing_validation": lambda m, i: f"const {m}Id_{i} = req.body.{m}_{i}",
    "promise_race": lambda m, i: f"{m}Cache_{i}.set(key_{i}, val_{i})",
}
_JS_NEW = {
    "prototype_pollution": lambda m, i: f"structuredClone({m}Defaults_{i})",
    "innerHTML": lambda m, i: f"{m}El_{i}.textContent = {m}Html_{i}",
    "missing_validation": lambda m, i: f"const {m}Id_{i} = validate{m.title()}(req.body.{m}_{i})",
    "promise_race": lambda m, i: f"await {m}Mutex_{i}.run(() => {m}Cache_{i}.set(key_{i}, val_{i}))",
}

# ---- TypeScript ----
_TS_OLD = {
    "unsafe_assertion": lambda m, i: f"{m}Data_{i} as {m.title()}Type_{i}",
    "any_leak": lambda m, i: f"{m}Param_{i}: any",
}
_TS_NEW = {
    "unsafe_assertion": lambda m, i: f"is{m.title()}_{i}({m}Data_{i}) ? {m}Data_{i} : null",
    "any_leak": lambda m, i: f"{m}Param_{i}: unknown",
}

# ---- C++ ----
_CPP_OLD = {
    "buffer_overflow": lambda m, i: f"return {m}_vec_{i}[idx_{i}];",
    "uaf": lambda m, i: f"delete {m}_ptr_{i};\n    return {m}_ptr_{i}->val_{i};",
    "format_string": lambda m, i: f'printf({m}_msg_{i});',
    "int_overflow": lambda m, i: f"new char[{m}_a_{i} + {m}_b_{i}]",
}
_CPP_NEW = {
    "buffer_overflow": lambda m, i: f"if (idx_{i} >= {m}_vec_{i}.size()) return std::nullopt;\n    return {m}_vec_{i}[idx_{i}];",
    "uaf": lambda m, i: f"auto val_{m}_{i} = {m}_ptr_{i}->val_{i};\n    delete {m}_ptr_{i};\n    {m}_ptr_{i} = nullptr;\n    return val_{m}_{i};",
    "format_string": lambda m, i: f'printf("%s", {m}_msg_{i});',
    "int_overflow": lambda m, i: f'if ({m}_a_{i} > SIZE_MAX - {m}_b_{i}) throw std::overflow_error("{m}_{i}");\n    new char[{m}_a_{i} + {m}_b_{i}]',
}

# ---- C ----
_C_OLD = {
    "strcpy": lambda m, i: f"strcpy({m}_dst_{i}, {m}_src_{i});",
    "double_free": lambda m, i: f"free({m}_p_{i});\n    free({m}_p_{i});",
    "uninit": lambda m, i: f"int {m}_x_{i};\n    return {m}_x_{i};",
    "off_by_one": lambda m, i: f"for ({m}_i_{i} = 0; {m}_i_{i} <= {m}_n_{i}; {m}_i_{i}++)",
}
_C_NEW = {
    "strcpy": lambda m, i: f'snprintf({m}_dst_{i}, sizeof({m}_dst_{i}), "%s", {m}_src_{i});',
    "double_free": lambda m, i: f"free({m}_p_{i});\n    {m}_p_{i} = NULL;",
    "uninit": lambda m, i: f"int {m}_x_{i} = 0;\n    return {m}_x_{i};",
    "off_by_one": lambda m, i: f"for ({m}_i_{i} = 0; {m}_i_{i} < {m}_n_{i}; {m}_i_{i}++)",
}

# ---- Rust ----
_RS_OLD = {
    "unwrap": lambda m, i: f"{m}_result_{i}.unwrap()",
    "unsafe_block": lambda m, i: f"unsafe {{ *{m}_ptr_{i}.add(idx_{i}) }}",
    "panic_instead_result": lambda m, i: f'panic!("{m} bad input {i}")',
}
_RS_NEW = {
    "unwrap": lambda m, i: f"{m}_result_{i}.ok_or({m}Error::Invalid_{i})?",
    "unsafe_block": lambda m, i: f"if idx_{i} >= {m}_len_{i} {{ return Err({m}Error::Bounds_{i}) }}\n    unsafe {{ *{m}_ptr_{i}.add(idx_{i}) }}",
    "panic_instead_result": lambda m, i: f"return Err({m}Error::BadInput_{i}.into())",
}

# ---- Go ----
_GO_OLD = {
    "goroutine_leak": lambda m, i: f"go {m}Worker_{i}()",
    "channel_deadlock": lambda m, i: f"{m}Ch_{i} <- val_{i}",
    "mutex_scope": lambda m, i: f"{m}Map_{i}.data[key_{i}] = val_{i}",
}
_GO_NEW = {
    "goroutine_leak": lambda m, i: f"go {m}Worker_{i}(ctx_{i})",
    "channel_deadlock": lambda m, i: f"select {{\ncase {m}Ch_{i} <- val_{i}:\ndefault:\n    return fmt.Errorf(\"{m}_{i}: channel full\")\n}}",
    "mutex_scope": lambda m, i: f"{m}Map_{i}.mu.Lock()\n    defer {m}Map_{i}.mu.Unlock()\n    {m}Map_{i}.data[key_{i}] = val_{i}",
}

# ---- Multi-file old/new per language ----
_MULTI_OLD = {
    "python": {"sqli": lambda m, i: f"def {m}_query_{i}():\n        return None", "pickle": lambda m, i: f"def {m}_load_{i}():\n        return None", "path_traversal": lambda m, i: f"def {m}_serve_{i}():\n        return None", "eval_exec": lambda m, i: f"def {m}_config_{i}():\n        return None", "race_thread": lambda m, i: f"def {m}_inc_{i}():\n        return None", "asyncio_lock": lambda m, i: f"async def {m}_push_{i}():\n        return None", "except_pass": lambda m, i: f"def {m}_handle_{i}():\n        return None"},
    "javascript": {"prototype_pollution": lambda m, i: f"function {m}Merge_{i}() {{ return null; }}", "innerHTML": lambda m, i: f"function {m}Render_{i}() {{ return null; }}", "missing_validation": lambda m, i: f"function {m}Validate_{i}() {{ return null; }}", "promise_race": lambda m, i: f"async function {m}Cache_{i}() {{ return null; }}"},
    "typescript": {"unsafe_assertion": lambda m, i: f"function {m}Handle_{i}(): null {{ return null; }}", "any_leak": lambda m, i: f"function {m}Api_{i}(): any {{ return null; }}"},
    "cpp": {"buffer_overflow": lambda m, i: f"auto {m}_get_{i}() -> std::nullopt_t {{ return std::nullopt; }}", "uaf": lambda m, i: f"int {m}_read_{i}() {{ return 0; }}", "format_string": lambda m, i: f"void {m}_log_{i}() {{}}", "int_overflow": lambda m, i: f"char* {m}_alloc_{i}() {{ return nullptr; }}"},
    "c": {"strcpy": lambda m, i: f"void {m}_copy_{i}(void) {{ }}", "double_free": lambda m, i: f"void {m}_cleanup_{i}(void) {{ }}", "uninit": lambda m, i: f"int {m}_read_{i}(void) {{ return 0; }}", "off_by_one": lambda m, i: f"void {m}_loop_{i}(void) {{ }}"},
    "rust": {"unwrap": lambda m, i: f"fn {m}_parse_{i}() -> Option<()> {{ None }}", "unsafe_block": lambda m, i: f"fn {m}_read_{i}() -> Result<(), ()> {{ Err(()) }}", "panic_instead_result": lambda m, i: f"fn {m}_validate_{i}() -> Result<(), ()> {{ Err(()) }}"},
    "go": {"goroutine_leak": lambda m, i: f"func {m}Worker_{i}() {{}}", "channel_deadlock": lambda m, i: f"func {m}Send_{i}() {{}}", "mutex_scope": lambda m, i: f"func {m}Write_{i}() {{}}"},
}
_MULTI_NEW = {
    "python": {"sqli": lambda m, i: f"def {m}_query_{i}():\n        return {m}_result_{i}", "pickle": lambda m, i: f"def {m}_load_{i}():\n        return {m}_parsed_{i}", "path_traversal": lambda m, i: f"def {m}_serve_{i}():\n        return {m}_safe_path_{i}", "eval_exec": lambda m, i: f"def {m}_config_{i}():\n        return {m}_validated_{i}", "race_thread": lambda m, i: f"def {m}_inc_{i}():\n        return {m}_count_{i}", "asyncio_lock": lambda m, i: f"async def {m}_push_{i}():\n        return {m}_added_{i}", "except_pass": lambda m, i: f"def {m}_handle_{i}():\n        return {m}_processed_{i}"},
    "javascript": {"prototype_pollution": lambda m, i: f"function {m}Merge_{i}() {{ return {m}Result_{i}; }}", "innerHTML": lambda m, i: f"function {m}Render_{i}() {{ return {m}Safe_{i}; }}", "missing_validation": lambda m, i: f"function {m}Validate_{i}() {{ return {m}Valid_{i}; }}", "promise_race": lambda m, i: f"async function {m}Cache_{i}() {{ return {m}Cached_{i}; }}"},
    "typescript": {"unsafe_assertion": lambda m, i: f"function {m}Handle_{i}(): {m.title()}Result_{i} {{ return validated_{m}_{i}; }}", "any_leak": lambda m, i: f"function {m}Api_{i}(): {m.title()}Typed_{i} {{ return typed_{m}_{i}; }}"},
    "cpp": {"buffer_overflow": lambda m, i: f"auto {m}_get_{i}() -> std::optional<int> {{ return {m}_vec_{i}.at(0); }}", "uaf": lambda m, i: f"int {m}_read_{i}() {{ return {m}_safe_{i}; }}", "format_string": lambda m, i: f"void {m}_log_{i}() {{ spdlog::info(\"{m}_{i}\"); }}", "int_overflow": lambda m, i: f"char* {m}_alloc_{i}() {{ return new char[{m}_safe_{i}]; }}"},
    "c": {"strcpy": lambda m, i: f"void {m}_copy_{i}(char *dst, size_t n, const char *src) {{ snprintf(dst, n, \"%s\", src); }}", "double_free": lambda m, i: f"void {m}_cleanup_{i}(void *p) {{ free(p); }}", "uninit": lambda m, i: f"int {m}_read_{i}(void) {{ int v = 0; return v; }}", "off_by_one": lambda m, i: f"void {m}_loop_{i}(int n) {{ for (int j = 0; j < n; j++) {{}} }}"},
    "rust": {"unwrap": lambda m, i: f"fn {m}_parse_{i}() -> Result<(), {m}Error_{i}> {{ Ok(()) }}", "unsafe_block": lambda m, i: f"fn {m}_read_{i}() -> Result<u8, {m}Error_{i}> {{ Ok(0) }}", "panic_instead_result": lambda m, i: f"fn {m}_validate_{i}() -> Result<(), {m}Error_{i}> {{ Ok(()) }}"},
    "go": {"goroutine_leak": lambda m, i: f"func {m}Worker_{i}(ctx context.Context) {{}}", "channel_deadlock": lambda m, i: f"func {m}Send_{i}(ch chan<- int, v int) error {{ return nil }}", "mutex_scope": lambda m, i: f"func {m}Write_{i}(mu *sync.Mutex) {{}}"},
}

_VULN_OLD: dict[str, dict[str, object]] = {
    "python": _PY_OLD, "javascript": _JS_OLD, "typescript": _TS_OLD,
    "cpp": _CPP_OLD, "c": _C_OLD, "rust": _RS_OLD, "go": _GO_OLD,
}
_VULN_NEW: dict[str, dict[str, object]] = {
    "python": _PY_NEW, "javascript": _JS_NEW, "typescript": _TS_NEW,
    "cpp": _CPP_NEW, "c": _C_NEW, "rust": _RS_NEW, "go": _GO_NEW,
}
_WRONG_FIX: dict[str, dict[str, object]] = {
    "python": _PY_WRONG,
}


PYTHON_BUGS = [BugTemplate(k, {"sqli": "CWE-89", "pickle": "CWE-502", "path_traversal": "CWE-22", "eval_exec": "CWE-94", "race_thread": "CWE-362", "asyncio_lock": "CWE-362", "except_pass": "CWE-390"}[k], {"sqli": "SQL injection via string concat", "pickle": "Unsafe pickle deserialization", "path_traversal": "Path traversal in file open", "eval_exec": "eval on config expression", "race_thread": "Race on shared counter", "asyncio_lock": "Async race without lock", "except_pass": "Silent exception swallow"}[k], "python", "py") for k in _PY_OLD]

JS_BUGS = [BugTemplate(k, {"prototype_pollution": "CWE-1321", "innerHTML": "CWE-79", "missing_validation": "CWE-20", "promise_race": "CWE-362"}[k], {"prototype_pollution": "Prototype pollution via merge", "innerHTML": "XSS via innerHTML", "missing_validation": "Missing body validation", "promise_race": "Uncoordinated cache write"}[k], "javascript", "js") for k in _JS_OLD]

TS_BUGS = [BugTemplate(k, {"unsafe_assertion": "CWE-704", "any_leak": "CWE-704"}[k], {"unsafe_assertion": "Unsafe type assertion", "any_leak": "any propagates to API"}[k], "typescript", "ts") for k in _TS_OLD]

CPP_BUGS = [BugTemplate(k, {"buffer_overflow": "CWE-787", "uaf": "CWE-416", "format_string": "CWE-134", "int_overflow": "CWE-190"}[k], {"buffer_overflow": "Out of bounds vector access", "uaf": "Use after free", "format_string": "printf format string bug", "int_overflow": "Integer overflow before alloc"}[k], "cpp", "cpp") for k in _CPP_OLD]

C_BUGS = [BugTemplate(k, {"strcpy": "CWE-787", "double_free": "CWE-415", "uninit": "CWE-457", "off_by_one": "CWE-193"}[k], {"strcpy": "Unbounded strcpy", "double_free": "Double free", "uninit": "Uninitialized read", "off_by_one": "Off-by-one loop"}[k], "c", "c") for k in _C_OLD]

RUST_BUGS = [BugTemplate(k, {"unwrap": "CWE-754", "unsafe_block": "CWE-119", "panic_instead_result": "CWE-754"}[k], {"unwrap": "unwrap in library path", "unsafe_block": "unsafe without bounds check", "panic_instead_result": "panic on bad input"}[k], "rust", "rs") for k in _RS_OLD]

GO_BUGS = [BugTemplate(k, {"goroutine_leak": "CWE-401", "channel_deadlock": "CWE-833", "mutex_scope": "CWE-362"}[k], {"goroutine_leak": "Goroutine leak without ctx", "channel_deadlock": "Unbuffered send deadlock", "mutex_scope": "Mutex not held during write"}[k], "go", "go") for k in _GO_OLD]


EPISTEMIC_BY_LANG: dict[str, list[tuple[str, str]]] = {
    "python": [
        ("How do I use sqlite3 parameterized queries to avoid SQL injection?", "Use `cur.execute(\"SELECT * FROM t WHERE id = ?\", (user_id,))`. Never interpolate user strings into SQL text."),
        ("When should asyncio.Lock guard shared async state?", "Create `self._lock = asyncio.Lock()` and wrap mutations with `async with self._lock:` because list append is not atomic across tasks."),
        ("How do I safely join paths with pathlib without traversal?", "Use `base = Path(base_dir).resolve()` then `target = (base / name).resolve()` and reject if `base not in target.parents`."),
    ],
    "javascript": [
        ("How do I avoid prototype pollution when merging objects?", "Use `Object.create(null)` as target or validate keys with `Object.hasOwn()` before assign; avoid recursive merge from untrusted JSON."),
        ("What is the safe alternative to innerHTML for user text?", "Use `textContent` or createTextNode. If HTML is required, sanitize with a vetted library first."),
    ],
    "typescript": [
        ("How do I narrow unknown API JSON without unsafe casts?", "Define a type guard `function isUser(v: unknown): v is User` and check fields before use."),
    ],
    "cpp": [
        ("When should I use std::optional instead of raw pointer returns?", "Return `std::optional<T>` for maybe-absent values to avoid dereferencing invalid pointers."),
    ],
    "c": [
        ("How do I safely copy strings with snprintf?", "Call `snprintf(dst, sizeof dst, \"%s\", src)` and check truncation return value."),
    ],
    "rust": [
        ("How do I propagate errors with ? instead of unwrap?", "Return `Result<T, E>` and use `?` inside fallible functions; map errors with `.map_err()`."),
    ],
    "go": [
        ("How do I prevent goroutine leaks with context?", "Pass `ctx context.Context`, select on `<-ctx.Done()` in workers, and cancel from caller with `context.WithCancel`."),
    ],
}
