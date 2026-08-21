from __future__ import annotations

from dataclasses import dataclass, field

from mango_cot import (
    ReasoningNeed,
    ReasoningState,
    classify_reasoning_need,
    compress_reasoning_state,
    run_reasoning_cycle,
)
from mango_cot.parse import parse_reasoning_payload


@dataclass
class FakeResult:
    tool_name: str
    success: bool
    body: str = ""
    error: str | None = None


@dataclass
class FakeContext:
    goal: str = "task"
    tool_results: list = field(default_factory=list)
    previous_actions: list = field(default_factory=list)
    relevant_files: list = field(default_factory=list)
    verification_failed_tests: list = field(default_factory=list)
    verification_impl_paths: list = field(default_factory=list)
    verification_impl_symbols: list = field(default_factory=list)
    verification_collection_error: bool = False


@dataclass
class FakeCompletion:
    text: str


class FakeRunner:
    def __init__(self, outputs: list[str] | None = None) -> None:
        self.outputs = list(outputs or [])
        self.prompts: list[str] = []

    def complete(self, prompt: str, **kwargs) -> FakeCompletion:
        self.prompts.append(prompt)
        if not self.outputs:
            raise RuntimeError("no reasoning outputs left")
        return FakeCompletion(self.outputs.pop(0))


def test_classify_none_for_simple_task() -> None:
    need = classify_reasoning_need("Say hi.", FakeContext())
    assert need is ReasoningNeed.NONE


def test_classify_short_after_one_failure() -> None:
    ctx = FakeContext(tool_results=[FakeResult("read_file", False, error="not found")])
    assert classify_reasoning_need("Read the file.", ctx) is ReasoningNeed.SHORT


def test_classify_extended_after_two_failures() -> None:
    ctx = FakeContext(
        tool_results=[
            FakeResult("read_file", False, error="a"),
            FakeResult("read_file", False, error="b"),
        ]
    )
    assert classify_reasoning_need("Debug the missing import.", ctx) is ReasoningNeed.EXTENDED


def test_classify_extended_for_multi_file_verification_failures() -> None:
    """Two failed tests across two impl files must be extended on the first fail."""
    ctx = FakeContext(
        verification_failed_tests=["test_feature.py::test_discount", "test_feature.py::test_money"],
        verification_impl_paths=["app/pricing.py", "app/format.py"],
        verification_impl_symbols=["discount", "money"],
    )
    assert classify_reasoning_need("Fix the tests.", ctx) is ReasoningNeed.EXTENDED


def test_classify_extended_for_collection_error() -> None:
    ctx = FakeContext(verification_collection_error=True)
    assert classify_reasoning_need("Fix unique().", ctx) is ReasoningNeed.EXTENDED


def test_classify_extended_for_multi_file_goal_before_verification() -> None:
    """Goal naming two files/symbols is extended even with empty verification state."""
    task = (
        "Implementiere ein Feature über mehrere Dateien: discount(price, pct) in app/pricing.py "
        "must return price * (1 - pct), and money(n) in app/format.py must return $n with two decimals."
    )
    ctx = FakeContext()
    assert not ctx.verification_failed_tests
    assert not ctx.verification_impl_paths
    assert not ctx.verification_impl_symbols
    assert not ctx.tool_results
    assert classify_reasoning_need(task, ctx) is ReasoningNeed.EXTENDED


def test_extract_goal_targets_collects_all_symbols_and_files() -> None:
    from mango_cot import extract_goal_targets

    targets = extract_goal_targets(
        "Implementiere ein Feature über mehrere Dateien: discount(price, pct) in app/pricing.py "
        "must return price * (1 - pct), and money(n) in app/format.py must return $n with two decimals."
    )
    assert "discount" in targets.symbols
    assert "money" in targets.symbols
    assert any(path.endswith("pricing.py") for path in targets.files)
    assert any(path.endswith("format.py") for path in targets.files)


def test_run_reasoning_cycle_none_skips_model() -> None:
    runner = FakeRunner(['{"next_action": "should not be used"}'])
    state = ReasoningState(goal="Say hi.")
    raw = run_reasoning_cycle(state, FakeContext(), runner, need=ReasoningNeed.NONE)
    assert raw == ""
    assert runner.prompts == []
    assert state.next_action == ""


def test_run_reasoning_cycle_short_extracts_next_action() -> None:
    runner = FakeRunner(
        ['{"next_action": "read src/main.py", "known_facts": ["entry is main.py"]}']
    )
    state = ReasoningState(goal="Find the entrypoint")
    ctx = FakeContext(tool_results=[FakeResult("search_code", False, error="no matches")])
    run_reasoning_cycle(state, ctx, runner, need=ReasoningNeed.SHORT)
    assert state.next_action == "read src/main.py"
    assert "entry is main.py" in state.known_facts
    assert state.failed_attempts  # synced from context
    assert len(runner.prompts) == 1
    assert "[Mango reasoning cycle]" in runner.prompts[0]


def test_run_reasoning_cycle_extended_updates_several_fields() -> None:
    payload = """
    {
      "next_action": "open lib/util.py",
      "known_facts": ["tests fail on import"],
      "decisions": ["inspect util before rewriting"],
      "assumptions": ["util is the import root"],
      "open_questions": ["which symbol is missing?"],
      "failed_attempts": ["grep for Util"]
    }
    """
    runner = FakeRunner([payload])
    state = ReasoningState(goal="Fix import error")
    ctx = FakeContext(
        tool_results=[
            FakeResult("search_code", False, error="no matches"),
            FakeResult("read_file", False, error="missing"),
        ]
    )
    run_reasoning_cycle(state, ctx, runner, need=ReasoningNeed.EXTENDED)
    assert state.next_action.startswith("open lib/util.py")
    assert state.decisions
    assert state.assumptions
    assert state.open_questions
    assert len(state.failed_attempts) >= 2


def test_compress_reasoning_state_is_compact() -> None:
    state = ReasoningState(
        goal="Fix the bug",
        known_facts=["A" * 400, "B" * 400, "C" * 400],
        decisions=["rewrite the parser"],
        failed_attempts=["read missing.txt", "read also_missing.txt"],
        open_questions=["where is the config?"],
        next_action="read config.yaml",
    )
    summary = compress_reasoning_state(state, max_chars=500)
    assert len(summary) <= 500
    assert "Next:" in summary
    assert "Chain:" not in summary
    assert "thought2" not in summary
    assert "A" * 400 not in summary
    raw = "".join(state.known_facts + state.failed_attempts)
    assert len(summary) < len(raw)


def test_thought_for_ui_is_plain_language() -> None:
    from mango_cot import thought_for_ui

    state = ReasoningState(
        goal="Create a CSV tool",
        known_facts=["The file does not exist yet"],
        next_action="write_file",
        cycle_summaries=["thought2: next=write_file; fact=The file does not exist yet"],
    )
    text = thought_for_ui(state)
    assert "write_file" in text
    assert "Chain:" not in text
    assert "thought2" not in text
    assert "next=" not in text


def test_parse_reasoning_payload_from_fenced_json() -> None:
    text = 'Sure.\n```json\n{"next_action": "retry"}\n```\n'
    assert parse_reasoning_payload(text)["next_action"] == "retry"


def test_run_chained_cumulative_visibility_and_summary_only() -> None:
    from mango_cot import CoTEngine

    runner = FakeRunner(
        outputs=[
            '{"thought":"STEP_ONE_UNIQUE","next_action":"inspect","known_facts":["a"]}',
            '{"thought":"STEP_TWO_UNIQUE","next_action":"edit","known_facts":["b"]}',
            '{"thought":"STEP_THREE_UNIQUE","next_action":"verify","known_facts":["c"]}',
            '{"summary":"FINAL_SUMMARY_ONLY","next_action":"run_tests","verify_plan":["assert"]}',
        ]
    )
    engine = CoTEngine("Fix the bug")
    seen: list[tuple[int, str]] = []

    def on_step(i: int, text: str) -> None:
        seen.append((i, text))

    summary = engine.run_chained(
        runner,
        steps=3,
        verify_level="deep",
        verify_hint="verify first",
        on_step=on_step,
    )

    assert len(runner.prompts) == 4  # 3 steps + summarize
    assert "STEP_ONE_UNIQUE" in runner.prompts[1]
    assert "STEP_ONE_UNIQUE" in runner.prompts[2]
    assert "STEP_TWO_UNIQUE" in runner.prompts[2]
    assert "STEP_ONE_UNIQUE" in runner.prompts[3]
    assert "STEP_TWO_UNIQUE" in runner.prompts[3]
    assert "STEP_THREE_UNIQUE" in runner.prompts[3]
    assert "FINAL_SUMMARY_ONLY" in summary
    assert "STEP_ONE_UNIQUE" not in summary
    assert "STEP_TWO_UNIQUE" not in summary
    assert len(seen) == 3
