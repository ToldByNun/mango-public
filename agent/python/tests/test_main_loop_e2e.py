from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from mango_agent import Agent, AgentLimits, Orchestrator, StopReason, log_loop_metrics
from mango_cot import REASONING_MARKER
from mango_cot.classify import GoalTargets, extract_goal_targets
from test_agent_loop import FakeCompletion, FakeModelRunner


def _write_verify_config(root: Path) -> None:
    command = f"{sys.executable} -m pytest -q --tb=short --rootdir=. -p no:cacheprovider"
    (root / "mango.verify.json").write_text(
        json.dumps({"test": {"command": command, "timeout": 60}}),
        encoding="utf-8",
    )


def _write_files(root: Path, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _tool(name: str, **arguments: object) -> str:
    return f"<tool_call={name} : {json.dumps(arguments)}>"


COMPLEX_GOAL = (
    "Implementiere ein Feature über mehrere Dateien: discount(price, pct) in app/pricing.py "
    "must return price * (1 - pct), and money(n) in app/format.py must return $n with two decimals."
)
_WRONG_PRICING = "def discount(price, pct):\n    return price + pct\n"
_RIGHT_PRICING = "def discount(price, pct):\n    return price * (1 - pct)\n"
_RIGHT_FORMAT = "def money(n):\n    return f'${n:.2f}'\n"


def _limits(**overrides) -> AgentLimits:
    values = dict(
        max_iterations=12,
        max_runtime_seconds=60,
        max_reasoning_cycles=20,
        max_fix_attempts=5,
        max_epistemic_iterations=6,
        max_prompt_chars=24_000,
    )
    values.update(overrides)
    return AgentLimits(**values)


def _setup_complex_project(root: Path) -> tuple[Path, Path]:
    _write_files(
        root,
        {
            "app/__init__.py": "",
            "app/pricing.py": "def discount(price, pct):\n    return price\n",
            "app/format.py": "def money(n):\n    return str(n)\n",
            "test_feature.py": (
                "from app.pricing import discount\nfrom app.format import money\n\n\n"
                "def test_discount():\n    assert discount(100, 0.1) == 90\n\n\n"
                "def test_money():\n    assert money(90) == '$90.00'\n"
            ),
        },
    )
    _write_verify_config(root)
    return root / "app" / "pricing.py", root / "app" / "format.py"


def _complex_outputs(variant: str, pricing: Path, fmt: Path) -> list[str]:
    if variant == "3run":
        return [
            _tool("write_file", path=str(pricing), content=_WRONG_PRICING),
            _tool("write_file", path=str(pricing), content=_RIGHT_PRICING),
            _tool("write_file", path=str(fmt), content=_RIGHT_FORMAT),
            "Implemented discount and money across app/pricing.py and app/format.py.",
        ]
    if variant == "2run":
        return [
            _tool("write_file", path=str(pricing), content=_WRONG_PRICING)
            + "\n"
            + _tool("write_file", path=str(fmt), content=_RIGHT_FORMAT),
            _tool("write_file", path=str(pricing), content=_RIGHT_PRICING),
            "Implemented discount and money across app/pricing.py and app/format.py.",
        ]
    if variant == "1run":
        return [
            _tool("write_file", path=str(pricing), content=_RIGHT_PRICING)
            + "\n"
            + _tool("write_file", path=str(fmt), content=_RIGHT_FORMAT),
            "Implemented discount and money across app/pricing.py and app/format.py.",
        ]
    raise ValueError(f"unknown complex variant: {variant}")


def _pre_write_lookup_blob(state) -> str:
    parts: list[str] = []
    for entry in state.tool_results:
        if entry.tool_name in {"write_file", "edit_file", "edit_symbol"}:
            break
        if entry.tool_name == "codebase_lookup":
            parts.append(entry.body)
    return "\n".join(parts)


def _first_write_step(result):
    for step in result.steps:
        if any(call.name in {"write_file", "edit_file", "edit_symbol"} for call in step.tool_calls):
            return step
    return None


def _run_complex_variant(tmp_path: Path, variant: str):
    pricing, fmt = _setup_complex_project(tmp_path)
    runner = FakeModelRunner(_complex_outputs(variant, pricing, fmt))
    orch = Orchestrator(runner, workspace=tmp_path, limits=_limits())
    result = orch.run(COMPLEX_GOAL)
    return result, orch, runner, pricing, fmt


ROUNDING_GOAL = (
    "Implementiere discount(price, pct) in app/pricing.py as price * (1 - pct), "
    "and money(n) in app/format.py as a dollar string with two decimals."
)
ROUNDING_FACT = "round discount to cents before money truncates"
_NAIVE_DISCOUNT = "def discount(price, pct):\n    return price * (1 - pct)\n"
_ROUNDED_DISCOUNT = "def discount(price, pct):\n    return round(price * (1 - pct), 2)\n"
_CENTS_MONEY = (
    "def money(n):\n"
    "    cents = int(n * 100)\n"
    "    return f'${cents // 100}.{cents % 100:02d}'\n"
)
_EXTENDED_ROUNDING_JSON = json.dumps(
    {
        "next_action": "write discount and money",
        "known_facts": ["money() uses int(n * 100) and truncates fractional cents"],
        "decisions": ["quantize discount to 2 decimals before formatting"],
        "assumptions": [ROUNDING_FACT],
        "open_questions": [],
        "failed_attempts": [],
    }
)


def _compressed_reasoning_block(prompt: str) -> str:
    marker = "## Compressed reasoning summary"
    if marker not in prompt:
        return ""
    rest = prompt.split(marker, 1)[1]
    if "\n## " in rest:
        rest = rest.split("\n## ", 1)[0]
    return rest


def _prompt_has_rounding_dependency(prompt: str) -> bool:
    """True only if compress_reasoning_state() put the coupling into the action prompt."""
    return ROUNDING_FACT in _compressed_reasoning_block(prompt)


class RoundingAwareFakeRunner:
    """Action writes follow the compressed reasoning in the prompt, not the turn index."""

    def __init__(self, pricing: Path, fmt: Path) -> None:
        self.pricing = pricing
        self.fmt = fmt
        self.prompts: list[str] = []
        self.reasoning_prompts: list[str] = []
        self.write_used_rounding: list[bool] = []

    def complete(self, prompt: str, **kwargs) -> FakeCompletion:
        if REASONING_MARKER in prompt:
            self.reasoning_prompts.append(prompt)
            if "Mode: EXTENDED" in prompt:
                return FakeCompletion(text=_EXTENDED_ROUNDING_JSON)
            return FakeCompletion(text='{"next_action": "continue"}')

        self.prompts.append(prompt)
        if "Verification passed" in prompt:
            return FakeCompletion(text="Implemented discount and money.")
        used = _prompt_has_rounding_dependency(prompt)
        self.write_used_rounding.append(used)
        discount = _ROUNDED_DISCOUNT if used else _NAIVE_DISCOUNT
        return FakeCompletion(
            text=_tool("write_file", path=str(self.pricing), content=discount)
            + "\n"
            + _tool("write_file", path=str(self.fmt), content=_CENTS_MONEY)
        )


def _setup_rounding_project(root: Path) -> tuple[Path, Path]:
    _write_files(
        root,
        {
            "app/__init__.py": "",
            "app/pricing.py": "def discount(price, pct):\n    return price\n",
            "app/format.py": "def money(n):\n    return str(n)\n",
            "test_feature.py": (
                "from app.pricing import discount\nfrom app.format import money\n\n\n"
                "def test_discount():\n    assert discount(100, 0.1) == 90\n\n\n"
                "def test_money():\n    assert money(90) == '$90.00'\n\n\n"
                "def test_discount_money_cents():\n"
                "    # 100 * (1 - 0.9) is 9.999... as a float; money truncates cents.\n"
                "    assert money(discount(100, 0.9)) == '$10.00'\n"
            ),
        },
    )
    _write_verify_config(root)
    return root / "app" / "pricing.py", root / "app" / "format.py"


def _set_goal_multi_target(enabled: bool) -> None:
    import mango_cot.classify as classify_mod

    if enabled:
        classify_mod.extract_goal_targets = extract_goal_targets
    else:
        classify_mod.extract_goal_targets = lambda _task: GoalTargets()


def _run_rounding_variant(tmp_path: Path, *, goal_multi_target: bool):
    pricing, fmt = _setup_rounding_project(tmp_path)
    runner = RoundingAwareFakeRunner(pricing, fmt)
    _set_goal_multi_target(goal_multi_target)
    try:
        orch = Orchestrator(runner, workspace=tmp_path, limits=_limits())
        result = orch.run(ROUNDING_GOAL)
    finally:
        _set_goal_multi_target(True)
    return result, orch, runner, pricing, fmt


def fake_web_research(query: str) -> dict:
    blob = "RESEARCH_BLOB " * 80
    return {
        "query": query,
        "results": [
            {
                "title": "json.dumps — JSON encoder",
                "url": "https://docs.python.org/3/library/json.html",
                "snippet": blob + " json.dumps(obj, *, skipkeys=False)",
            }
        ],
    }


def test_e2e_simple_edit_one_function(tmp_path: Path) -> None:
    greet = tmp_path / "greet.py"
    _write_files(
        tmp_path,
        {
            "greet.py": "def greet(name):\n    return f'hi {name}'\n",
            "test_greet.py": "from greet import greet\n\n\ndef test_greet():\n    assert greet('Ada') == 'Hello, Ada!'\n",
        },
    )
    _write_verify_config(tmp_path)

    runner = FakeModelRunner(
        [
            _tool("codebase_lookup", query="Where is function greet defined?"),
            _tool(
                "edit_file",
                path=str(greet),
                old_string="return f'hi {name}'",
                new_string="return f'Hello, {name}!'",
            ),
            "Updated greet() to return Hello, {name}!.",
        ]
    )
    orch = Orchestrator(runner, workspace=tmp_path, limits=_limits())
    result = orch.run("Change the greet function in greet.py so it returns 'Hello, {name}!'.")
    log_loop_metrics(result, "simple_edit_one_function")

    assert result.stop_reason == StopReason.COMPLETED
    assert greet.read_text(encoding="utf-8") == "def greet(name):\n    return f'Hello, {name}!'\n"
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert "codebase_lookup" in names
    assert "edit_file" in names
    assert "ask_epistemic" not in names
    assert result.metrics.iterations == result.iterations
    assert result.metrics.final_prompt_chars > 0
    assert result.metrics.tool_call_count == 2
    assert result.metrics.epistemic_calls == 0
    assert result.metrics.verification_runs >= 1
    assert result.metrics.verification_failures == 0
    assert orch.agent.tool_registry.has("codebase_lookup")
    assert orch.agent.tool_registry.has("ask_epistemic")


def test_e2e_medium_unknown_api_triggers_epistemic(tmp_path: Path) -> None:
    target = tmp_path / "jsonutil.py"
    _write_files(
        tmp_path,
        {
            "test_jsonutil.py": (
                "import json\nfrom jsonutil import to_json\n\n\n"
                "def test_to_json():\n    assert json.loads(to_json({'a': 1})) == {'a': 1}\n"
            ),
        },
    )
    _write_verify_config(tmp_path)
    impl = "import json\n\n\ndef to_json(obj):\n    return json.dumps(obj)\n"

    runner = FakeModelRunner(
        [
            _tool(
                "ask_epistemic",
                question="Does json.dumps exist in the json library, and what is the signature?",
            ),
            # Known stdlib cards short-circuit the nested sub-agent (no model call).
            _tool("write_file", path=str(target), content=impl),
            "Implemented to_json using json.dumps.",
        ]
    )
    orch = Orchestrator(
        runner,
        workspace=tmp_path,
        limits=_limits(),
        epistemic_web_backend=fake_web_research,
    )
    result = orch.run(
        "Implementiere Funktion to_json(obj) in jsonutil.py that serializes with the json library. "
        "If you are unsure about json.dumps, call ask_epistemic first."
    )
    log_loop_metrics(result, "medium_unknown_api_epistemic")

    assert result.stop_reason == StopReason.COMPLETED
    assert target.read_text(encoding="utf-8") == impl
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert names[0] == "ask_epistemic"
    assert "write_file" in names
    assert result.metrics.epistemic_calls >= 1
    # json.dumps is a known stdlib card → nested web/doc tools are skipped on purpose.
    assert result.metrics.epistemic_subagent_iterations == 0
    assert orch.agent.epistemic is not None
    assert orch.agent.epistemic.total_asks >= 1
    main_bodies = [entry.body for entry in orch.agent.context.state.tool_results]
    assert all("RESEARCH_BLOB" not in body for body in main_bodies)
    assert any("json.dumps" in body for body in main_bodies)


def test_e2e_complex_multifile_verification_fix_loop(tmp_path: Path) -> None:
    result, orch, runner, pricing, fmt = _run_complex_variant(tmp_path, "2run")
    log_loop_metrics(result, "complex_multifile_fix_loop")

    assert result.stop_reason == StopReason.COMPLETED
    assert pricing.read_text(encoding="utf-8") == _RIGHT_PRICING
    assert fmt.read_text(encoding="utf-8") == _RIGHT_FORMAT
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert names.count("write_file") == 3
    assert result.metrics.verification_runs == 2
    assert result.metrics.verification_failures == 1
    assert result.metrics.epistemic_calls == 0
    write_step = _first_write_step(result)
    assert write_step is not None
    assert write_step.reasoning_need == "extended"
    lookup_blob = _pre_write_lookup_blob(orch.agent.context.state)
    assert "discount" in lookup_blob
    assert "money" in lookup_blob
    first_prompt = runner.prompts[0]
    assert "pricing.py" in first_prompt
    assert "format.py" in first_prompt
    fail_prompt = runner.prompts[1]
    assert "## Verification" in fail_prompt
    assert "still failing" in fail_prompt
    assert "test_discount" in fail_prompt
    assert "pricing.py" in fail_prompt
    assert any("format.py" in path for path in orch.agent.context.state.relevant_files)
    assert orch.agent.context is not None
    verify_results = [entry for entry in orch.agent.context.state.tool_results if entry.tool_name == "verification"]
    assert any(not entry.success for entry in verify_results)
    assert any(entry.success for entry in verify_results)
    assert "passed" in (result.verification_report or "").lower()
    assert "fixed:" in (result.verification_report or "")


def test_e2e_complex_one_verification_run(tmp_path: Path) -> None:
    result, orch, runner, pricing, fmt = _run_complex_variant(tmp_path, "1run")
    log_loop_metrics(result, "complex_one_verification_run")

    assert result.stop_reason == StopReason.COMPLETED
    assert pricing.read_text(encoding="utf-8") == _RIGHT_PRICING
    assert fmt.read_text(encoding="utf-8") == _RIGHT_FORMAT
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert names.count("write_file") == 2
    assert result.metrics.verification_runs == 1
    assert result.metrics.verification_failures == 0
    write_step = _first_write_step(result)
    assert write_step is not None
    assert write_step.reasoning_need == "extended"
    lookup_blob = _pre_write_lookup_blob(orch.agent.context.state)
    assert "discount" in lookup_blob
    assert "money" in lookup_blob
    first_prompt = runner.prompts[0]
    assert "pricing.py" in first_prompt
    assert "format.py" in first_prompt
    verify_results = [entry for entry in orch.agent.context.state.tool_results if entry.tool_name == "verification"]
    assert len(verify_results) == 1
    assert verify_results[0].success is True


def test_e2e_complex_legacy_three_verification_runs(tmp_path: Path) -> None:
    result, orch, runner, pricing, fmt = _run_complex_variant(tmp_path, "3run")
    log_loop_metrics(result, "complex_legacy_three_runs")

    assert result.stop_reason == StopReason.COMPLETED
    assert pricing.read_text(encoding="utf-8") == _RIGHT_PRICING
    assert fmt.read_text(encoding="utf-8") == _RIGHT_FORMAT
    names = [call.name for step in result.steps for call in step.tool_calls]
    assert names.count("write_file") == 3
    assert result.metrics.verification_runs == 3
    assert result.metrics.verification_failures == 2
    write_step = _first_write_step(result)
    assert write_step is not None
    assert write_step.reasoning_need == "extended"
    lookup_blob = _pre_write_lookup_blob(orch.agent.context.state)
    assert "discount" in lookup_blob
    assert "money" in lookup_blob
    first_prompt = runner.prompts[0]
    assert "pricing.py" in first_prompt
    assert "format.py" in first_prompt


def test_multi_tool_calls_allowed_after_multifile_verification_fail(tmp_path: Path) -> None:
    pricing = tmp_path / "app" / "pricing.py"
    fmt = tmp_path / "app" / "format.py"
    _write_files(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/pricing.py": "def discount(price, pct):\n    return price\n",
            "app/format.py": "def money(n):\n    return str(n)\n",
            "test_feature.py": (
                "from app.pricing import discount\nfrom app.format import money\n\n\n"
                "def test_discount():\n    assert discount(100, 0.1) == 90\n\n\n"
                "def test_money():\n    assert money(90) == '$90.00'\n"
            ),
        },
    )
    _write_verify_config(tmp_path)
    runner = FakeModelRunner(
        [
            _tool("write_file", path=str(pricing), content="def discount(price, pct):\n    return price + pct\n"),
            _tool("write_file", path=str(pricing), content="def discount(price, pct):\n    return price * (1 - pct)\n")
            + "\n"
            + _tool("write_file", path=str(fmt), content="def money(n):\n    return f'${n:.2f}'\n"),
            "Fixed both files.",
        ]
    )
    orch = Orchestrator(runner, workspace=tmp_path, limits=_limits())
    result = orch.run("Implementiere discount and money across two files.")
    assert result.stop_reason == StopReason.COMPLETED
    assert result.steps[1].reasoning_need == "extended"
    fail_prompt = runner.prompts[1]
    assert "multiple edit_symbol/write_file" in fail_prompt
    assert orch.agent.context is not None
    assert orch.agent.context.state.allow_multi_edit is False
    assert pricing.read_text(encoding="utf-8").count("(1 - pct)") == 1
    assert "$" in fmt.read_text(encoding="utf-8")
    assert result.steps[1].tool_calls[0].name == "write_file"
    assert result.steps[1].tool_calls[1].name == "write_file"


def test_auto_lookup_unseen_symbol_after_verification_fail(tmp_path: Path) -> None:
    pricing = tmp_path / "app" / "pricing.py"
    _write_files(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/pricing.py": "def discount(price, pct):\n    return price\n",
            "app/format.py": "def money(n):\n    return str(n)\n",
            "test_feature.py": (
                "from app.pricing import discount\nfrom app.format import money\n\n\n"
                "def test_discount():\n    assert discount(100, 0.1) == 90\n\n\n"
                "def test_money():\n    assert money(90) == '$90.00'\n"
            ),
        },
    )
    _write_verify_config(tmp_path)
    runner = FakeModelRunner(
        [
            _tool("write_file", path=str(pricing), content="def discount(price, pct):\n    return price + pct\n"),
            "still working",
        ]
    )
    orch = Orchestrator(runner, workspace=tmp_path, limits=_limits(max_iterations=2))
    result = orch.run("Implementiere discount and money.")
    assert orch.agent.context is not None
    assert result.steps[1].reasoning_need == "extended"
    lookup_bodies = [
        entry.body for entry in orch.agent.context.state.tool_results if entry.tool_name == "codebase_lookup"
    ]
    assert any("money" in body for body in lookup_bodies)
    assert any("format.py" in path for path in orch.agent.context.state.relevant_files)
    assert result.metrics.verification_failures >= 1


def test_e2e_complex_three_variants_five_runs(tmp_path_factory) -> None:
    expected = {
        "3run": {"verification_runs": 3, "verification_failures": 2},
        "2run": {"verification_runs": 2, "verification_failures": 1},
        "1run": {"verification_runs": 1, "verification_failures": 0},
    }
    protocol: list[dict] = []
    print(
        "[Mango variant protocol] variant | run | runs_to_green | fails | "
        "pre_write_lookup_both | classify_before_write | goal_multi_target",
        flush=True,
    )
    for variant, expect in expected.items():
        for run_id in range(1, 6):
            tmp_path = tmp_path_factory.mktemp(f"complex_{variant}_{run_id}")
            result, orch, runner, _pricing, _fmt = _run_complex_variant(tmp_path, variant)
            write_step = _first_write_step(result)
            lookup_blob = _pre_write_lookup_blob(orch.agent.context.state)
            first_prompt = runner.prompts[0] if runner.prompts else ""
            row = {
                "variant": variant,
                "run": run_id,
                "runs_to_green": result.metrics.verification_runs,
                "verification_failures": result.metrics.verification_failures,
                "stop": result.stop_reason.value,
                "pre_write_lookup_both": "discount" in lookup_blob and "money" in lookup_blob,
                "classify_before_write": write_step.reasoning_need if write_step else None,
                "goal_multi_target": True,
                "relevant_files_both_before_write": "pricing.py" in first_prompt and "format.py" in first_prompt,
            }
            protocol.append(row)
            print(
                f"[Mango variant {variant} {run_id}/5] runs={row['runs_to_green']} "
                f"fails={row['verification_failures']} "
                f"pre_write_lookup_both={row['pre_write_lookup_both']} "
                f"classify_before_write={row['classify_before_write']} "
                f"goal_multi_target={row['goal_multi_target']}",
                flush=True,
            )
            assert result.stop_reason == StopReason.COMPLETED
            assert row["runs_to_green"] == expect["verification_runs"]
            assert row["verification_failures"] == expect["verification_failures"]
            assert row["pre_write_lookup_both"]
            assert row["classify_before_write"] == "extended"
            assert row["relevant_files_both_before_write"]

    print("[Mango variant protocol summary]")
    print(
        f"{'variant':<6} {'run':<4} {'runs_to_green':<14} {'fails':<6} "
        f"{'pre_write_lookup_both':<23} {'classify_before_write':<22} {'goal_multi_target'}",
        flush=True,
    )
    for row in protocol:
        print(
            f"{row['variant']:<6} {row['run']:<4} {row['runs_to_green']:<14} "
            f"{row['verification_failures']:<6} {str(row['pre_write_lookup_both']):<23} "
            f"{str(row['classify_before_write']):<22} {row['goal_multi_target']}",
            flush=True,
        )
    assert len(protocol) == 15


def test_e2e_rounding_dependency_reasoning_depth_five_runs(tmp_path_factory) -> None:
    print(
        "[Mango rounding protocol] mode | run | verify_runs | fails | "
        "first_write_rounded | reasoning_in_first_prompt | first_need",
        flush=True,
    )
    protocol: list[dict] = []
    for enabled, label in ((True, "2b_on"), (False, "2b_off")):
        for run_id in range(1, 6):
            tmp_path = tmp_path_factory.mktemp(f"rounding_{label}_{run_id}")
            result, orch, runner, pricing, fmt = _run_rounding_variant(
                tmp_path, goal_multi_target=enabled
            )
            first_prompt = runner.prompts[0] if runner.prompts else ""
            write_step = _first_write_step(result)
            row = {
                "mode": label,
                "run": run_id,
                "stop": result.stop_reason.value,
                "verify_runs": result.metrics.verification_runs,
                "fails": result.metrics.verification_failures,
                "first_write_rounded": bool(runner.write_used_rounding and runner.write_used_rounding[0]),
                "reasoning_in_first_prompt": _prompt_has_rounding_dependency(first_prompt),
                "first_need": write_step.reasoning_need if write_step else None,
                "pricing_has_round": "round(" in pricing.read_text(encoding="utf-8"),
            }
            protocol.append(row)
            print(
                f"[Mango rounding {label} {run_id}/5] runs={row['verify_runs']} "
                f"fails={row['fails']} first_write_rounded={row['first_write_rounded']} "
                f"reasoning_in_first_prompt={row['reasoning_in_first_prompt']} "
                f"need={row['first_need']}",
                flush=True,
            )
            assert result.stop_reason == StopReason.COMPLETED
            if enabled:
                assert row["fails"] == 0
                assert row["verify_runs"] == 1
                assert row["first_write_rounded"]
                assert row["reasoning_in_first_prompt"]
                assert row["first_need"] == "extended"
                assert row["pricing_has_round"]
                assert ROUNDING_FACT in " ".join(orch.agent.cot.state.assumptions)
            else:
                assert row["fails"] >= 1
                assert not row["first_write_rounded"]
                assert not row["reasoning_in_first_prompt"]
                assert row["first_need"] == "none"
                lookup_blob = _pre_write_lookup_blob(orch.agent.context.state)
                assert "discount" in lookup_blob and "money" in lookup_blob

    print("[Mango rounding protocol summary]")
    print(
        f"{'mode':<8} {'run':<4} {'vruns':<6} {'fails':<6} "
        f"{'first_write_rounded':<20} {'reason_in_prompt':<18} {'first_need'}",
        flush=True,
    )
    for row in protocol:
        print(
            f"{row['mode']:<8} {row['run']:<4} {row['verify_runs']:<6} {row['fails']:<6} "
            f"{str(row['first_write_rounded']):<20} {str(row['reasoning_in_first_prompt']):<18} "
            f"{row['first_need']}",
            flush=True,
        )
    assert len(protocol) == 10


def test_main_loop_stops_when_deadline_already_passed() -> None:
    runner = FakeModelRunner(["should not be consumed"])
    agent = Agent(runner, max_iterations=5, max_runtime_seconds=30)
    result = agent.run("Say hi.", deadline=time.monotonic() - 1)
    log_loop_metrics(result, "deadline_already_passed")
    assert result.stop_reason == StopReason.TIMEOUT
    assert result.iterations == 0
    assert result.metrics.tool_call_count == 0
    assert runner.prompts == []
