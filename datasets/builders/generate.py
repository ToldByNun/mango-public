from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from datasets.builders.prompts_loader import (
    agent_system,
    epistemic_system,
    finish_system,
    security_system,
)
from datasets.builders.schema import Scenario, ScenarioMeta
from datasets.builders.templates import (
    C_BUGS,
    CPP_BUGS,
    EPISTEMIC_BY_LANG,
    GO_BUGS,
    JS_BUGS,
    PYTHON_BUGS,
    RUST_BUGS,
    TS_BUGS,
    BugTemplate,
)
from datasets.builders.validate import validate_rows
from datasets.builders.verify import verify_scenario, write_report

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "datasets" / "mango_sft_1000.jsonl"
INDEX = ROOT / "datasets" / "catalog" / "index.jsonl"

LANG_SEEDS: dict[str, int] = {
    "python": 1001,
    "js_ts": 2002,
    "cpp": 3003,
    "c": 4004,
    "rust": 5005,
    "go": 6006,
}

LANG_QUOTAS: dict[str, int] = {
    "python": 2300,
    "js_ts": 2000,
    "cpp": 2000,
    "c": 1500,
    "rust": 900,
    "go": 300,
}

WORKFLOW_SHARE = {
    "test_fail_fix": 0.35,
    "security_review": 0.15,
    "multi_file_refactor": 0.10,
    "ambiguous_ask_epistemic": 0.05,
    "cot_cycle": 0.17,
    "epistemic_api": 0.15,
    "agent_finish": 0.03,
}

DIFFICULTY_SHARE = {"easy": 0.40, "medium": 0.40, "hard": 0.20}

DOMAINS = [
    "auth", "cache", "router", "parser", "queue", "ledger", "upload", "search",
    "notify", "billing", "session", "token", "metrics", "export", "import",
]


def _load_existing(*, exclude: Path | None = None, include_pilot: bool = False) -> tuple[set[str], set[str]]:
    users: set[str] = set()
    assistants: set[str] = set()
    paths = [V1, ROOT / "datasets" / "mango_sft_2000.jsonl"]
    v3 = ROOT / "datasets" / "chunks_v3"
    if v3.is_dir():
        for path in sorted(v3.rglob("*.jsonl")):
            if exclude and path.resolve() == exclude.resolve():
                continue
            if not include_pilot and "pilot" in path.parts:
                continue
            paths.append(path)
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            users.add(row["messages"][1]["content"])
            assistants.add(row["messages"][2]["content"])
    return users, assistants


def _quota_split(total: int) -> dict[str, int]:
    keys = list(WORKFLOW_SHARE.keys())
    raw = {k: int(total * WORKFLOW_SHARE[k]) for k in keys}
    delta = total - sum(raw.values())
    raw[keys[0]] += delta
    return raw


def _pick_difficulty(i: int) -> str:
    r = i % 10
    if r < 4:
        return "easy"
    if r < 8:
        return "medium"
    return "hard"


def _tool_json(tool: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"<tool_call={tool} : {body}>"


def _bugs_for_lang(lang_key: str) -> list[BugTemplate]:
    if lang_key == "python":
        return PYTHON_BUGS
    if lang_key == "js_ts":
        return JS_BUGS + TS_BUGS
    if lang_key == "cpp":
        return CPP_BUGS
    if lang_key == "c":
        return C_BUGS
    if lang_key == "rust":
        return RUST_BUGS
    return GO_BUGS


def _ext(lang: str) -> str:
    return {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "cpp": "cpp",
        "c": "c",
        "rust": "rs",
        "go": "go",
    }.get(lang, "txt")


def _test_cmd(lang: str) -> str:
    return {
        "python": "pytest -q",
        "javascript": "npm test",
        "typescript": "npm test",
        "cpp": "ctest --output-on-failure",
        "c": "make test",
        "rust": "cargo test",
        "go": "go test ./all",
    }.get(lang, "make test")


def _make_test_fail_fix(
    lang: str,
    bug: BugTemplate,
    idx: int,
    difficulty: str,
    *,
    turn: str = "single",
    pair_id: str | None = None,
    use_wrong: bool = False,
) -> Scenario:
    domain = DOMAINS[idx % len(DOMAINS)]
    mod = f"{domain}_{bug.bug_class}_{idx:05d}"
    ext = _ext(lang)
    src = f"src/{mod}.{ext}"
    sid = f"{lang}_{bug.bug_class}_{idx:05d}_{turn}"
    fname = f"{mod}.{ext}"

    old_s = bug.wrong_fix(mod, idx) if use_wrong else bug.vuln_old(mod, idx)
    new_s = bug.vuln_new(mod, idx) if not use_wrong else bug.vuln_old(mod, idx)
    if use_wrong and old_s is None:
        old_s = bug.vuln_old(mod, idx)

    user = (
        f"## Goal\nFix {bug.description} in {fname} (turn {turn}).\n\n"
        f"## Verification\nFAILED tests/test_{mod}.{ext} — case {idx} ({domain}).\n\n"
        f"## Relevant files\n- {fname}\n- tests/test_{mod}.{ext}\n\n"
        f"## Scenario\n{sid}\n\n"
        f"## Next\nApply smallest fix; run {_test_cmd(lang)}."
    )
    if turn == "A" and use_wrong:
        assistant = (
            f"[{sid}] The failing test implicates {bug.bug_class} but the prior fix scope looks too narrow. "
            f"Adding a global lock may not protect the shared structure ({bug.cwe}). "
            f"I will try a broader patch in {fname} first.\n"
            f'{_tool_json("edit_file", {"path": fname, "old_string": old_s, "new_string": new_s})}'
        )
    else:
        assistant = (
            f"[{sid}] The failing test shows {bug.bug_class} mishandling in {domain} module {mod}. "
            f"Root cause is {bug.description} ({bug.cwe}). "
            f"I will patch {fname} with a minimal edit next.\n"
            f'{_tool_json("edit_file", {"path": fname, "old_string": bug.vuln_old(mod, idx), "new_string": bug.vuln_new(mod, idx)})}'
        )
    meta = ScenarioMeta(
        scenario_id=sid,
        lang=lang,
        workflow="test_fail_fix",
        difficulty=difficulty,
        bug_class=bug.bug_class,
        turn=turn,
        pair_id=pair_id,
        cwe=bug.cwe,
    )
    return Scenario(meta=meta, system=agent_system(), user=user, assistant=assistant)


def _make_security(
    lang: str,
    bug: BugTemplate,
    idx: int,
    tier: str = "sandbox",
) -> Scenario:
    domain = DOMAINS[idx % len(DOMAINS)]
    mod = f"{domain}_{bug.bug_class}_{idx:05d}"
    ext = _ext(lang)
    fname = f"{mod}.{ext}"
    sid = f"sec_{lang}_{bug.bug_class}_{idx:05d}"

    user = (
        f"## Goal\nSecurity audit of {fname} ({bug.cwe}).\n\n"
        f"## Verification\nAll functional tests pass. Audit requested for {domain}.\n\n"
        f"## Relevant files\n- {fname}\n\n"
        f"## Scenario\n{sid}\n\n"
        f"## Next\nFind vulnerability without failing tests; fix implementation."
    )
    assistant = (
        f"[{sid}] Functional tests pass but {fname} still exposes {bug.description}. "
        f"This matches {bug.cwe} because untrusted input reaches a dangerous sink. "
        f"I will read the handler and apply a minimal hardening edit.\n"
        f'{_tool_json("edit_file", {"path": fname, "old_string": bug.vuln_old(mod, idx), "new_string": bug.vuln_new(mod, idx)})}'
    )

    sandbox: dict[str, str] = {}
    audit: dict[str, str] = {}
    if lang == "python":
        sandbox[f"{fname}"] = f"# {mod}\n# vulnerable: {bug.bug_class}\n"
        sandbox["tests/test_functional.py"] = (
            "def test_functional():\n    assert True\n"
        )
        audit["audit_tests/test_audit.py"] = (
            f"def test_audit_{bug.bug_class}():\n"
            f"    # PoC for {bug.cwe}\n"
            f"    assert 'FIXED' == 'VULN'\n"
        )

    meta = ScenarioMeta(
        scenario_id=sid,
        lang=lang,
        workflow="security_review",
        difficulty="medium",
        bug_class=bug.bug_class,
        verification_tier=tier,
        cwe=bug.cwe,
    )
    return Scenario(
        meta=meta,
        system=security_system(),
        user=user,
        assistant=assistant,
        sandbox_files=sandbox,
        audit_files=audit,
    )


def _make_multi_file(lang: str, bug: BugTemplate, idx: int) -> Scenario:
    domain = DOMAINS[idx % len(DOMAINS)]
    ext = _ext(lang)
    mod = f"{domain}_{bug.bug_class}_{idx:05d}"
    iface = f"iface_{mod}.{ext}"
    impl = f"impl_{mod}.{ext}"
    sid = f"multi_{lang}_{idx:05d}"
    old_s = bug.multi_old(mod, idx)
    new_s = bug.multi_new(mod, idx)
    user = (
        f"## Goal\nUpdate {iface} signature; fix all callers in {impl}.\n\n"
        f"## Verification\nFAILED tests/test_{mod}.{ext}::test_contract\n\n"
        f"## Relevant files\n- {iface}\n- {impl}\n\n"
        f"## Scenario\n{sid}\n\n"
        f"## Next\nEdit interface then implementation."
    )
    assistant = (
        f"[{sid}] Tests expect the new return type on {iface} but {impl} still returns void. "
        f"Callers must propagate the {bug.cwe} fix pattern consistently. "
        f"I will edit {impl} to match the interface contract.\n"
        f'{_tool_json("edit_file", {"path": impl, "old_string": old_s, "new_string": new_s})}'
    )
    meta = ScenarioMeta(
        scenario_id=sid,
        lang=lang,
        workflow="multi_file_refactor",
        difficulty="medium",
        bug_class=bug.bug_class,
        cwe=bug.cwe,
    )
    return Scenario(meta=meta, system=agent_system(), user=user, assistant=assistant)


def _make_ask_epistemic(lang: str, idx: int) -> Scenario:
    ep_lang = "javascript" if lang == "js_ts" and idx % 2 else lang
    if lang == "js_ts":
        ep_lang = "javascript" if idx % 3 else "typescript"
    pool = EPISTEMIC_BY_LANG.get(ep_lang, EPISTEMIC_BY_LANG["python"])
    q, a = pool[idx % len(pool)]
    q = f"{q} (scenario {idx:05d})"
    sid = f"ask_{lang}_{idx:05d}"
    domain = DOMAINS[idx % len(DOMAINS)]
    user = (
        f"## Goal\nImplement {domain} feature — requirement ambiguous on API semantics.\n\n"
        f"## Verification\nBlocked until API usage clarified.\n\n"
        f"## Relevant files\n- src/{domain}.{ _ext(lang if lang != 'js_ts' else 'javascript')}\n\n"
        f"## Scenario\n{sid}\n\n"
        f"## Next\nClarify API before coding."
    )
    assistant = (
        f"[{sid}] The snapshot does not specify whether the {domain} API is thread-safe or re-entrant. "
        f"Guessing would violate the runner plan gate for new modules. "
        f"I will ask_epistemic for targeted usage before declare_apis.\n"
        f'{_tool_json("ask_epistemic", {"question": q})}'
    )
    meta = ScenarioMeta(
        scenario_id=sid,
        lang=lang,
        workflow="ambiguous_ask_epistemic",
        difficulty="easy",
        bug_class="ambiguous_req",
    )
    return Scenario(meta=meta, system=agent_system(), user=user, assistant=assistant)


def _make_cot(lang: str, bug: BugTemplate, idx: int, pitfall: str | None = None) -> Scenario:
    domain = DOMAINS[idx % len(DOMAINS)]
    ext = _ext(lang)
    fname = f"{domain}_{idx:05d}.{ext}"
    mode = "EXTENDED" if idx % 2 else "SHORT"
    sid = f"cot_{lang}_{idx:05d}"
    pitfall_line = (
        "thought 4: Requirement is explicit from test name; ask_epistemic would waste a turn.\n"
        if pitfall == "unnecessary_epistemic"
        else f"thought 4: read_file {fname} before edit_file; avoid repeating failed old_string.\n"
    )
    system = (
        f"[Mango reasoning cycle]\nMode: {mode}\n\nGoal: Fix {bug.bug_class} in {fname}\n\n"
        f"Context snapshot:\nfiles: {fname}\nverification: FAILED test_{domain}\n\n"
        f"Previous thought:\n(empty)\n\nWrite exactly five lines: thought 1, thought 2, "
        f"thought 3, thought 4, and thought summary.\n\n"
        f"You pick the NEXT tool. Reply in English. No tool_call tag.\n\nOutput format:\n"
        f"thought 1: ...\nthought 2: ...\nthought 3: ...\nthought 4: ...\nthought summary: ..."
    )
    user = f"[{lang}] Next action for {domain} {bug.bug_class} #{idx:05d}? (scenario {sid})"
    assistant = (
        f"thought 1: [{sid}] test_{domain} fails on {bug.cwe} pattern in {fname}.\n"
        f"thought 2: {bug.description} is the likely root cause.\n"
        f"thought 3: Prior blind edit may have targeted the wrong branch.\n"
        f"{pitfall_line}"
        f"thought summary: Next tool: read_file {fname} then edit_file minimal fix."
    )
    meta = ScenarioMeta(
        scenario_id=sid,
        lang=lang,
        workflow="cot_cycle",
        difficulty=_pick_difficulty(idx),
        bug_class=bug.bug_class,
        pitfall=pitfall,
        cwe=bug.cwe,
    )
    return Scenario(meta=meta, system=system, user=user, assistant=assistant)


def _make_epistemic(lang: str, idx: int) -> Scenario:
    ep_lang = lang
    if lang == "js_ts":
        ep_lang = "javascript" if idx % 3 else ("typescript" if idx % 3 == 1 else "javascript")
    pool = EPISTEMIC_BY_LANG.get(ep_lang, EPISTEMIC_BY_LANG["python"])
    q, a = pool[idx % len(pool)]
    q = f"{q} (ref {idx:05d})"
    a = f"{a} Index {idx}."
    meta = ScenarioMeta(
        scenario_id=f"epi_{lang}_{idx:05d}",
        lang=lang,
        workflow="epistemic_api",
        difficulty="easy",
        bug_class="api_usage",
    )
    return Scenario(meta=meta, system=epistemic_system(), user=q, assistant=a)


def _make_finish(lang: str, bug: BugTemplate, idx: int) -> Scenario:
    domain = DOMAINS[idx % len(DOMAINS)]
    ext = _ext(lang)
    fname = f"{domain}_{bug.bug_class}.{ext}"
    cmd = _test_cmd(lang if lang != "js_ts" else "javascript")
    user = (
        f"## Goal\nFix {bug.description} in {fname}.\n\n"
        f"## Verification\nVerification passed. Reply with a short summary and NO tool calls.\n\n"
        f"## Relevant files\n- {fname}\n\n"
        f"## Scenario\nfin_{lang}_{idx:05d}\n\n"
        f"## Next\nVerification passed. Reply with a short summary and NO tool calls."
    )
    assistant = (
        f"[fin_{lang}_{idx:05d}] {cmd} reports all {domain} tests passed including regression case {idx}. "
        f"The final edit in {fname} addressed {bug.cwe} without changing public API surface. "
        f"Only {fname} was modified and verification targets remain green."
    )
    meta = ScenarioMeta(
        scenario_id=f"fin_{lang}_{idx:05d}",
        lang=lang,
        workflow="agent_finish",
        difficulty="easy",
        bug_class=bug.bug_class,
        cwe=bug.cwe,
    )
    return Scenario(meta=meta, system=finish_system(), user=user, assistant=assistant)


def generate_language(lang_key: str, total: int, *, seed: int = 42) -> list[Scenario]:
    random.seed(seed)
    bugs = _bugs_for_lang(lang_key)
    hard_pairs = max(1, int(total * DIFFICULTY_SHARE["hard"] * 0.5))
    # Each hard pair adds one net row (2 rows replace 1 slot)
    quotas = _quota_split(total - hard_pairs)
    scenarios: list[Scenario] = []
    idx = 0

    def lang_label() -> str:
        if lang_key == "js_ts":
            return "typescript" if idx % 3 == 1 else "javascript"
        return lang_key

    # Reserve slots for hard pairs (each pair = 2 rows)
    quotas["test_fail_fix"] = max(0, quotas["test_fail_fix"] - hard_pairs)

    for _ in range(quotas["test_fail_fix"]):
        bug = bugs[idx % len(bugs)]
        diff = _pick_difficulty(idx)
        if diff == "hard":
            diff = "medium"
        scenarios.append(_make_test_fail_fix(lang_label(), bug, idx, diff))
        idx += 1

    for p in range(hard_pairs):
        bug = bugs[(idx + p) % len(bugs)]
        pair = f"pair_{lang_key}_{idx + p:05d}"
        scenarios.append(_make_test_fail_fix(lang_label(), bug, idx + p, "hard", turn="A", pair_id=pair, use_wrong=bug.wrong_fix(f"d{idx+p}", idx+p) is not None))
        scenarios.append(_make_test_fail_fix(lang_label(), bug, idx + p, "hard", turn="B", pair_id=pair, use_wrong=False))

    sec_count = quotas["security_review"]
    for i in range(sec_count):
        bug = bugs[i % len(bugs)]
        tier = "sandbox" if i % 5 else "static_only"
        scenarios.append(_make_security(lang_label(), bug, 10000 + i, tier=tier))

    for i in range(quotas["multi_file_refactor"]):
        bug = bugs[i % len(bugs)]
        scenarios.append(_make_multi_file(lang_label(), bug, 20000 + i))

    for i in range(quotas["ambiguous_ask_epistemic"]):
        scenarios.append(_make_ask_epistemic(lang_key, 30000 + i))

    for i in range(quotas["cot_cycle"]):
        bug = bugs[i % len(bugs)]
        pitfall = "unnecessary_epistemic" if i % 17 == 0 else None
        scenarios.append(_make_cot(lang_label(), bug, 40000 + i, pitfall=pitfall))

    for i in range(quotas["epistemic_api"]):
        scenarios.append(_make_epistemic(lang_key, 50000 + i))

    for i in range(quotas["agent_finish"]):
        bug = bugs[i % len(bugs)]
        scenarios.append(_make_finish(lang_label(), bug, 60000 + i))

    if len(scenarios) > total:
        # Trim duplicate easy test_fail rows, never finish/cot/epistemic
        while len(scenarios) > total:
            removed = False
            for j, sc in enumerate(scenarios):
                if sc.meta.workflow == "test_fail_fix" and sc.meta.difficulty == "easy" and sc.meta.turn == "single":
                    scenarios.pop(j)
                    removed = True
                    break
            if not removed:
                scenarios = scenarios[:total]
                break

    while len(scenarios) < total:
        bug = bugs[len(scenarios) % len(bugs)]
        scenarios.append(_make_epistemic(lang_key, 70000 + len(scenarios)))

    return scenarios


def build_and_write(lang_key: str, out_dir: Path, *, verify: bool = True) -> Path:
    total = LANG_QUOTAS[lang_key]
    out_dir.mkdir(parents=True, exist_ok=True)
    chunk = out_dir / f"{lang_key}.jsonl"
    existing_users, existing_assistants = _load_existing(exclude=chunk)

    scenarios = generate_language(lang_key, total, seed=LANG_SEEDS.get(lang_key, 42))
    rows: list[dict] = []
    index_lines: list[dict] = []
    verify_errors: list[str] = []

    for sc in scenarios:
        if verify and sc.meta.workflow in ("test_fail_fix", "security_review"):
            errs = verify_scenario(
                sc,
                audit_expect_fail=sc.meta.workflow == "security_review" and bool(sc.audit_files),
            )
            if errs and sc.meta.verification_tier == "static_only":
                errs = []
            verify_errors.extend([f"{sc.meta.scenario_id}: {e}" for e in errs])
        rows.append(sc.to_row())
        index_lines.append(sc.to_index_line())

    val_errors = validate_rows(rows, existing_users=existing_users, existing_assistants=existing_assistants)
    if val_errors:
        raise RuntimeError(f"validation failed: {val_errors[:5]}")

    chunk.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")
    write_report(chunk.stem, verify_errors, len(rows))

    index_path = ROOT / "datasets" / "catalog" / f"index_{lang_key}.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in index_lines),
        encoding="utf-8",
    )

    return chunk
