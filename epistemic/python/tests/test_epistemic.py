from __future__ import annotations

from dataclasses import dataclass

from mango_cot import REASONING_MARKER
from mango_epistemic import EpistemicEngine, ask_epistemic
from mango_epistemic.parse import parse_epistemic_result
from mango_epistemic.research_tools import doc_lookup, inspect_symbol, package_source_lookup


@dataclass
class FakeCompletion:
    text: str


class FakeRunner:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def complete(self, prompt: str, **kwargs) -> FakeCompletion:
        if REASONING_MARKER in prompt:
            return FakeCompletion('{"next_action": "use web_research"}')
        self.prompts.append(prompt)
        if not self.outputs:
            raise RuntimeError("no outputs left")
        return FakeCompletion(self.outputs.pop(0))


def test_parse_epistemic_result_from_json() -> None:
    result = parse_epistemic_result(
        "Does json.dumps exist?",
        '{"exists": true, "signature": "dumps(obj)", "version": "3.12", "evidence": [{"source": "docs", "snippet": "dumps"}], "conflicts": null}',
    )
    assert result.exists is True
    assert result.signature == "dumps(obj)"
    assert result.version == "3.12"
    assert result.evidence[0].source == "docs"
    assert result.conflicts is None


def test_inspect_deque_returns_usage_card_not_args_kwargs() -> None:
    result = package_source_lookup("collections", "deque")
    assert result["exists"] is True
    blob = " ".join(
        [
            str(result.get("signature") or ""),
            str(result.get("usage_card") or ""),
            str(result.get("doc") or ""),
        ]
    )
    assert "append" in blob.lower()
    assert "popleft" in blob.lower() or "pop" in blob.lower()
    assert "maxlen" in blob.lower() or "iterable" in blob.lower()
    assert "(/, *args, **kwargs)" not in str(result.get("signature") or "")
    assert "usage_card" in result
    assert "deque" in result["usage_card"]
    assert "popleft" in result["usage_card"]
    assert "O(1)" in result["usage_card"]
    assert "namedtuple" not in result["usage_card"]


def test_parse_plain_usage_brief() -> None:
    brief = (
        "from collections import deque\n"
        "deque(iterable, maxlen=n) — maxlen auto-drops from the other end.\n"
        "append(x) / popleft() for a sliding window of timestamps."
    )
    result = parse_epistemic_result("How do I use collections.deque?", brief)
    assert result.exists is True
    assert result.details is not None
    assert "sliding window" in result.details
    assert result.signature is None


def test_package_source_lookup_inspects_stdlib() -> None:
    dumps = package_source_lookup("json", "dumps")
    parser = doc_lookup("argparse", "ArgumentParser")
    assert dumps["exists"] is True
    assert dumps["status"] == "ok"
    assert "dumps" in dumps["signature"]
    assert parser["exists"] is True
    assert "ArgumentParser" in parser["signature"]
    missing = inspect_symbol("definitely_not_a_real_package_xyz", "nope")
    assert missing["exists"] is False


def test_inspect_module_returns_callable_members_not_blurb() -> None:
    result = package_source_lookup("threading")
    assert result["exists"] is True
    assert "(" in result["signature"]
    names = {item["name"] for item in (result.get("members") or [])}
    assert "Lock" in names
    assert "Thread" in names
    lock = next(item for item in result["members"] if item["name"] == "Lock")
    assert "(" in lock["signature"]
    assert "java" not in (result.get("details") or "").lower()
    assert result["signature"].count("|") <= 6
    assert len(result["signature"]) < 400


def test_lookup_targets_from_rate_limiter_question() -> None:
    from mango_epistemic.targets import lookup_targets

    targets = lookup_targets("How do collections, threading, time, and deque work?")
    assert ("collections", "deque") in targets
    assert ("threading", "Lock") in targets
    assert ("time", "monotonic") in targets
    pooled = lookup_targets("Use concurrent.futures for parallel dispatch")
    assert ("concurrent.futures", "ThreadPoolExecutor") in pooled
    assert lookup_targets("uuid") == []
    assert lookup_targets("traceback") == []


def test_ask_epistemic_merges_declared_libraries_into_targets() -> None:
    runner = FakeRunner([])
    engine = EpistemicEngine(runner, max_iterations=2)
    result = engine.ask_epistemic(
        "How should the sliding window work?",
        libraries=["collections", "threading", "time"],
    )
    assert runner.prompts == []
    names = " ".join(result.looked_up).lower()
    assert "deque" in names
    assert "lock" in names
    assert "monotonic" in names


def test_ask_epistemic_skips_model_when_hints_cover_targets() -> None:
    runner = FakeRunner([])
    engine = EpistemicEngine(runner, max_iterations=2)
    result = engine.ask_epistemic("How do collections.deque and threading.Lock work?")
    assert runner.prompts == []
    assert engine.last_subagent_steps == 0
    blob = (result.details or "") + " " + (result.signature or "")
    assert "deque" in blob.lower()
    assert "lock" in blob.lower()
    assert "O(1)" in blob or "popleft" in blob.lower()


def test_ask_epistemic_prefetches_every_symbol() -> None:
    runner = FakeRunner([])
    engine = EpistemicEngine(runner, max_iterations=2)
    result = engine.ask_epistemic("How do collections.deque and threading.Lock work?")
    blob = (result.details or "") + " " + (result.signature or "")
    assert "deque" in blob.lower()
    assert "lock" in blob.lower()
    assert result.looked_up
    assert any("deque" in item for item in result.looked_up)


def test_ask_epistemic_isolated_summary_turn() -> None:
    runner = FakeRunner(
        [
            "statistics.median(data) returns the median of a numeric iterable. import statistics.",
        ]
    )
    engine = EpistemicEngine(runner, max_iterations=2)
    result = engine.ask_epistemic("How does statistics.median work?")

    assert result.exists is True
    compact = result.to_compact_dict()
    assert len(str(compact)) < 2_500
    assert engine.last_subagent_steps >= 1
    assert any("API Agent" in prompt for prompt in runner.prompts)
    assert any("median" in prompt.lower() for prompt in runner.prompts)


def test_ask_epistemic_uses_inspect_when_model_returns_intent() -> None:
    runner = FakeRunner(
        [
            "I will look up the signatures for json using the doc_lookup tool.",
        ]
    )
    engine = EpistemicEngine(runner, max_iterations=6)
    result = engine.ask_epistemic("Does json.dumps exist and what is the signature?")
    assert result.signature is not None
    assert "dumps" in result.signature
    assert "(" in result.signature
    assert not (result.details or "").lower().startswith("i will look up")
    assert "dumps" in (result.details or "").lower()


def test_ask_epistemic_function_wrapper() -> None:
    runner = FakeRunner(
        [
            '{"exists": false, "signature": null, "details": "not found", "version": null, "evidence": [], "conflicts": null}',
        ]
    )
    result = ask_epistemic("Does foo.bar exist?", model_runner=runner)
    assert result.exists is False
