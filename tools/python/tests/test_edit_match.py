"""Robust edit matching + write_file recovery for failed patches."""

from __future__ import annotations

from pathlib import Path

from mango_tools.fuzzy_edit import apply_replace, merge_failed_edit, recover_edit
from mango_tools.implementations.edit_file import edit_file


def test_anchor_match_tolerates_middle_drift() -> None:
    content = "def f():\n    a = 1\n    b = 2\n    return a + b\n"
    old = "def f():\n    a = 1\n    b = 99\n    return a + b\n"
    new = "def f():\n    a = 1\n    b = 2\n    return a * b\n"
    updated, _count, kind = apply_replace(
        content,
        old,
        new,
        allow_fuzzy=False,
        allow_whitespace=False,
        allow_indent=True,
    )
    assert kind == "anchor"
    assert "return a * b" in updated


def test_suffix_match_for_tail_replace() -> None:
    content = "def main():\n    print('hi')\n"
    old = "def main():\n    print('hi')\n"
    new = "def main():\n    print('hi')\n\nif __name__ == '__main__':\n    main()\n"
    updated, _count, kind = apply_replace(
        content,
        old,
        new,
        allow_fuzzy=False,
        allow_whitespace=True,
        allow_indent=True,
    )
    assert kind in {"exact", "suffix", "whitespace", "newlines"}
    assert "__main__" in updated


def test_merge_adds_missing_main_guard() -> None:
    existing = "def main():\n    return 1\n"
    new = (
        "def main():\n    return 1\n\n"
        "if __name__ == '__main__':\n    raise SystemExit(main())\n"
    )
    merged = merge_failed_edit(existing, "def main():\n    return 99\n", new)
    assert merged is not None
    assert "if __name__" in merged
    assert "def main()" in merged


def test_recover_edit_after_bad_old_string() -> None:
    existing = "def main():\n    print(1)\n"
    bad_old = "def main():\n    print(999)\n"
    new = (
        "def main():\n    print(1)\n\n"
        "if __name__ == '__main__':\n    main()\n"
    )
    recovered = recover_edit(existing, bad_old, new)
    assert recovered is not None
    text, kind = recovered
    assert "recovered" in kind
    assert "__main__" in text


def test_edit_file_after_read_allows_indent(tmp_path: Path) -> None:
    target = tmp_path / "wordstats.py"
    target.write_text("def f():\n\treturn 1\n", encoding="utf-8")
    abs_path = str(target.resolve())
    result = edit_file(
        "wordstats.py",
        "    return 1",
        "    return 2",
        _context={
            "workspace": str(tmp_path),
            "files_read": {abs_path},
            "require_grounded_edits": True,
        },
    )
    assert result["match"] in {"indent", "whitespace"}
    assert "fuzzy" not in result
    assert target.read_text(encoding="utf-8") == "def f():\n\treturn 2\n"
