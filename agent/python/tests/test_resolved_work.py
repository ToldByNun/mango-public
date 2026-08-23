from __future__ import annotations

from mango_agent.resolved_work import (
    closed_items,
    merge_resolved,
    thought_reasserts_resolved,
)


def test_closed_items_is_opaque_diff() -> None:
    before = [
        "a.cpp: Missing entry point: `int main(...)`",
        "a.cpp: Goal needs list/show inventory behavior",
    ]
    after = ["a.cpp: Goal needs list/show inventory behavior"]
    assert closed_items(before, after) == [
        "a.cpp: Missing entry point: `int main(...)`"
    ]


def test_thought_reasserts_any_resolved_claim() -> None:
    resolved = [
        "wordstats.py: Missing entry point: `if __name__ == '__main__'`",
        "util.rs: Missing entry point: `fn main()`",
        "svc.go: Function `Serve` looks incomplete (stub body — finish the logic)",
    ]
    hits = thought_reasserts_resolved(
        "The implementation status shows that wordstats.py is missing the "
        "if __name__ == '__main__' entry point.",
        resolved,
    )
    assert hits and "wordstats.py" in hits[0]

    rust_hits = thought_reasserts_resolved(
        "Hypothesis: util.rs still needs fn main before we can finish.",
        resolved,
    )
    assert rust_hits and "util.rs" in rust_hits[0]

    stub_hits = thought_reasserts_resolved(
        "Serve still looks incomplete with a stub body — finish the logic.",
        resolved,
    )
    assert stub_hits and "Serve" in stub_hits[0]


def test_merge_resolved_dedupes() -> None:
    base = ["file.py: Missing entry point: `x`"]
    out = merge_resolved(base, ["file.py: Missing entry point: `x`", "file.py: stub foo"])
    assert out == [
        "file.py: Missing entry point: `x`",
        "file.py: stub foo",
    ]
