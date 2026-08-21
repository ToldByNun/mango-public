from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "datasets" / ".verify_cache"
REPORTS = ROOT / "datasets" / "verify_reports"

FENCE_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)


def _run(cmd: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def extract_python_from_assistant(content: str) -> list[str]:
    return [m.group(2) for m in FENCE_RE.finditer(content) if (m.group(1) or "python") in ("python", "py")]


def verify_python_source(source: str, label: str) -> list[str]:
    errors: list[str] = []
    try:
        ast.parse(source)
        compile(source, f"<{label}>", "exec")
    except SyntaxError as exc:
        errors.append(f"{label}: syntax error: {exc}")
    return errors


def verify_python_snippets(snippets: list[str]) -> list[str]:
    errors: list[str] = []
    for i, src in enumerate(snippets):
        errors.extend(verify_python_source(src, f"snippet_{i}"))
    return errors


def verify_python_sandbox(sandbox_dir: Path) -> list[str]:
    errors: list[str] = []
    for py in sandbox_dir.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        errors.extend(verify_python_source(src, py.name))
    if (sandbox_dir / "tests").is_dir() or list(sandbox_dir.glob("test_*.py")):
        code, out = _run([sys.executable, "-m", "pytest", "-q"], sandbox_dir)
        if code != 0:
            errors.append(f"pytest failed ({code}): {out[:500]}")
    return errors


def verify_python_audit(sandbox_dir: Path, expect_audit_fail: bool) -> list[str]:
    audit = sandbox_dir / "audit_tests"
    if not audit.is_dir():
        return []
    code, out = _run([sys.executable, "-m", "pytest", "-q", str(audit)], sandbox_dir)
    if expect_audit_fail and code == 0:
        return ["audit_tests should fail on vulnerable code but passed"]
    if not expect_audit_fail and code != 0:
        return [f"audit_tests should pass after fix but failed: {out[:500]}"]
    return []


def verify_js_source(source: str, label: str) -> list[str]:
    if shutil.which("node"):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(source)
            path = Path(f.name)
        code, out = _run(["node", "--check", str(path)], path.parent)
        path.unlink(missing_ok=True)
        if code != 0:
            return [f"{label}: node --check failed: {out[:300]}"]
    return []


def verify_go_sandbox(sandbox_dir: Path) -> list[str]:
    errors: list[str] = []
    if not shutil.which("go"):
        return errors
    code, out = _run(["go", "vet", "./..."], sandbox_dir)
    if code != 0:
        errors.append(f"go vet: {out[:400]}")
    code, out = _run(["go", "test", "./..."], sandbox_dir)
    if code != 0:
        errors.append(f"go test: {out[:400]}")
    return errors


def verify_rust_source(source: str, label: str) -> list[str]:
    if not shutil.which("rustc"):
        return []
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lib.rs"
        path.write_text(source, encoding="utf-8")
        code, out = _run(["rustc", "--edition", "2021", "--crate-type", "lib", str(path)], Path(td))
        if code != 0:
            return [f"{label}: rustc failed: {out[:400]}"]
    return []


def verify_c_source(source: str, label: str, cpp: bool = False) -> list[str]:
    compiler = shutil.which("g++") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        return []
    with tempfile.TemporaryDirectory() as td:
        ext = ".cpp" if cpp else ".c"
        path = Path(td) / f"main{ext}"
        path.write_text(source, encoding="utf-8")
        cmd = [compiler, "-fsyntax-only"]
        if cpp:
            cmd.extend(["-std=c++17"])
        cmd.append(str(path))
        code, out = _run(cmd, Path(td))
        if code != 0:
            return [f"{label}: compile failed: {out[:400]}"]
    return []


def check_hard_pairs(index_lines: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    by_pair: dict[str, list[dict[str, Any]]] = {}
    for entry in index_lines:
        pid = entry.get("pair_id")
        if pid:
            by_pair.setdefault(pid, []).append(entry)
    for pid, entries in by_pair.items():
        turns = {e.get("turn") for e in entries}
        if turns != {"A", "B"}:
            errors.append(f"pair {pid}: expected turns A and B, got {turns}")
        langs = {e.get("lang") for e in entries}
        if len(langs) != 1:
            errors.append(f"pair {pid}: mixed langs {langs}")
    return errors


def verify_scenario(
    scenario: Any,
    *,
    audit_expect_fail: bool | None = None,
) -> list[str]:
    from datasets.builders.schema import Scenario

    if not isinstance(scenario, Scenario):
        return ["not a Scenario"]
    errors: list[str] = []
    lang = scenario.meta.lang

    if scenario.sandbox_files:
        CACHE.mkdir(parents=True, exist_ok=True)
        sbx = CACHE / scenario.meta.scenario_id
        if sbx.exists():
            shutil.rmtree(sbx)
        sbx.mkdir(parents=True)
        for rel, content in scenario.sandbox_files.items():
            dest = sbx / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        for rel, content in (scenario.audit_files or {}).items():
            dest = sbx / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")

        if lang == "python":
            errors.extend(verify_python_sandbox(sbx))
            if audit_expect_fail is not None:
                errors.extend(verify_python_audit(sbx, audit_expect_fail))
        elif lang == "go":
            errors.extend(verify_go_sandbox(sbx))
    else:
        snippets = extract_python_from_assistant(scenario.assistant)
        if lang == "python":
            errors.extend(verify_python_snippets(snippets))
        elif lang in ("javascript", "js"):
            for i, m in enumerate(FENCE_RE.finditer(scenario.assistant)):
                if m.group(1) in (None, "javascript", "js"):
                    errors.extend(verify_js_source(m.group(2), f"js_{i}"))
        elif lang == "rust":
            for i, m in enumerate(FENCE_RE.finditer(scenario.assistant)):
                if m.group(1) in (None, "rust", "rs"):
                    errors.extend(verify_rust_source(m.group(2), f"rust_{i}"))
        elif lang in ("cpp", "c++"):
            for i, m in enumerate(FENCE_RE.finditer(scenario.assistant)):
                if m.group(1) in (None, "cpp", "c++"):
                    errors.extend(verify_c_source(m.group(2), f"cpp_{i}", cpp=True))
        elif lang == "c":
            for i, m in enumerate(FENCE_RE.finditer(scenario.assistant)):
                if m.group(1) in (None, "c"):
                    errors.extend(verify_c_source(m.group(2), f"c_{i}", cpp=False))

    return errors


def write_report(chunk_name: str, errors: list[str], row_count: int) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    blocking = [e for e in errors if "syntax error" in e.lower()]
    report = {
        "chunk": chunk_name,
        "status": "ok" if not blocking else "fail",
        "errors": errors,
        "warnings": len(errors) - len(blocking),
        "row_count": row_count,
    }
    path = REPORTS / f"{chunk_name}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if not args:
        print("usage: verify.py --index catalog/index.jsonl", file=sys.stderr)
        return 1
    if args[0] == "--check-hard-pairs" and len(args) >= 2:
        index_path = Path(args[1])
        lines = [json.loads(l) for l in index_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        errs = check_hard_pairs(lines)
        if errs:
            for e in errs:
                print(e)
            return 1
        print(f"hard pairs OK ({len(lines)} index entries)")
        return 0
    print("verify.py: use via build pipeline (build_language.py)", file=sys.stderr)
    return 0


def verify_scenario_module(scenario: Any, **kwargs: Any) -> list[str]:
    return verify_scenario(scenario, **kwargs)


if __name__ == "__main__":
    raise SystemExit(main())
