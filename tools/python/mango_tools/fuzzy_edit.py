from __future__ import annotations

import difflib
import re

_FUZZY_RATIO = 0.86
_FUZZY_RATIO_SHORT = 0.78  # 1–3 line needles from small models
_AMBIGUOUS_DELTA = 0.04
_UNCHANGED = "file unchanged; tests still fail; change the implementation"
_MAIN_BLOCK = re.compile(
    r"(?m)^(if\s+__name__\s*==\s*['\"]__main__['\"]\s*:.*)$",
    re.DOTALL,
)


def apply_replace(
    content: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
    allow_fuzzy: bool = True,
    allow_whitespace: bool = False,
    allow_indent: bool = False,
) -> tuple[str, int, str]:
    """Replace old_string in content. Returns (updated, count, match_kind).

    Match ladder (first hit wins):
      exact → newlines → trailing-ws → ws-collapsed → indent →
      line-anchor → suffix → fuzzy
    """
    if old_string == new_string:
        raise ValueError(_UNCHANGED)
    if not old_string:
        raise ValueError("old_string is empty")

    count = content.count(old_string)
    if count:
        return (
            _commit_exact(content, old_string, new_string, count, replace_all),
            count if replace_all else 1,
            "exact",
        )

    normalized, newline = _newline_style(content)
    old_n = old_string.replace("\r\n", "\n").replace("\r", "\n")
    new_n = new_string.replace("\r\n", "\n").replace("\r", "\n")
    count = normalized.count(old_n)
    if count:
        updated = _commit_exact(normalized, old_n, new_n, count, replace_all)
        n = count if replace_all else 1
        return _restore_newlines(updated, newline), n, "newlines"

    relaxed = allow_whitespace or allow_fuzzy or allow_indent
    if relaxed:
        # Trailing-whitespace tolerant, indent must still match.
        span = _unique_normalized_span(normalized, old_n, strip_indent=False)
        if span is not None:
            start, end, original = span
            updated = normalized[:start] + _align_indent(original, new_n) + normalized[end:]
            return _restore_newlines(updated, newline), 1, "whitespace"

    if allow_whitespace:
        span = _unique_ws_collapsed_span(normalized, old_n)
        if span is not None:
            start, end, original = span
            updated = normalized[:start] + _align_indent(original, new_n) + normalized[end:]
            return _restore_newlines(updated, newline), 1, "whitespace"

    if allow_indent or allow_fuzzy:
        span = _unique_normalized_span(normalized, old_n, strip_indent=True)
        if span is not None:
            start, end, original = span
            updated = normalized[:start] + _align_indent(original, new_n) + normalized[end:]
            return _restore_newlines(updated, newline), 1, "indent"

    if allow_indent or allow_fuzzy or allow_whitespace:
        span = _unique_anchor_span(normalized, old_n)
        if span is not None:
            start, end, original = span
            updated = normalized[:start] + _align_indent(original, new_n) + normalized[end:]
            return _restore_newlines(updated, newline), 1, "anchor"

        span = _unique_suffix_span(normalized, old_n)
        if span is not None:
            start, end, original = span
            updated = normalized[:start] + _align_indent(original, new_n) + normalized[end:]
            return _restore_newlines(updated, newline), 1, "suffix"

    if not allow_fuzzy:
        hint = _nearest_snippet(normalized, old_n)
        raise ValueError(
            "old_string not found in file. read_file first and copy old_string exactly "
            "(no fuzzy/typo match)."
            + (f" Nearest snippet:\n{hint}" if hint else "")
            + " Suggested next tool: write_file with the complete corrected file."
        )

    span = _fuzzy_span(normalized, old_n)
    if span is not None:
        start, end, original = span
        updated = normalized[:start] + _align_indent(original, new_n) + normalized[end:]
        return _restore_newlines(updated, newline), 1, "fuzzy"

    hint = _nearest_snippet(normalized, old_n)
    raise ValueError(
        "old_string not found in file. Copy a unique snippet from the file, "
        "or call write_file with the complete file contents."
        + (f" Nearest snippet:\n{hint}" if hint else "")
        + " Suggested next tool: write_file for a full rewrite."
    )


def recover_edit(content: str, old_string: str, new_string: str) -> tuple[str, str] | None:
    """Best-effort recovery when a grounded edit failed — used by the agent fallback."""
    if not new_string:
        return None
    needle = old_string or ""
    if needle:
        try:
            updated, _count, kind = apply_replace(
                content,
                needle,
                new_string,
                allow_fuzzy=True,
                allow_whitespace=True,
                allow_indent=True,
            )
            return updated, f"recovered_{kind}"
        except ValueError:
            pass

    merged = merge_failed_edit(content, needle, new_string)
    if merged is not None:
        return merged, "recovered_merge"
    return None


def merge_failed_edit(existing: str, old_string: str, new_string: str) -> str | None:
    """Synthesize a full file when the model meant to patch but matching failed."""
    if not existing and new_string.strip():
        return new_string if _looks_like_module(new_string) else None

    # Full-file rewrite that mostly overlaps the current file.
    if _looks_like_module(new_string) and len(new_string) >= max(int(len(existing) * 0.5), 40):
        if _line_overlap_ratio(existing, new_string) >= 0.45 or not existing.strip():
            return new_string

    existing_has_main = bool(re.search(r"(?m)^if\s+__name__\s*==", existing))
    new_has_main = bool(re.search(r"(?m)^if\s+__name__\s*==", new_string))

    # Classic loop: add ``if __name__ == "__main__":`` after edits keep missing.
    if new_has_main and not existing_has_main:
        block = _extract_main_block(new_string)
        if block:
            return existing.rstrip() + "\n\n" + block.rstrip() + "\n"
        if new_string.strip().startswith("if __name__"):
            return existing.rstrip() + "\n\n" + new_string.strip() + "\n"

    # new_string is roughly the corrected full file.
    if _looks_like_module(new_string) and _line_overlap_ratio(existing, new_string) >= 0.7:
        if len(new_string) >= len(existing) * 0.8:
            return new_string

    return None


def _extract_main_block(text: str) -> str | None:
    match = _MAIN_BLOCK.search(text.replace("\r\n", "\n"))
    if not match:
        return None
    return match.group(1).rstrip() + "\n"


def _looks_like_module(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    hits = sum(1 for line in lines if line.startswith(("import ", "from ", "def ", "class ")))
    return hits >= 2 or (hits >= 1 and "if __name__" in text)


def _line_overlap_ratio(left: str, right: str) -> float:
    left_lines = {line.strip() for line in left.splitlines() if line.strip()}
    right_lines = {line.strip() for line in right.splitlines() if line.strip()}
    if not left_lines or not right_lines:
        return 0.0
    return len(left_lines & right_lines) / max(len(left_lines), 1)


def _nearest_snippet(content: str, needle: str, *, radius: int = 2) -> str:
    if not content or not needle:
        return ""
    lines = content.splitlines()
    needle_lines = [line.strip() for line in needle.splitlines() if line.strip()]
    if not needle_lines or not lines:
        return ""
    target = needle_lines[0]
    best_i = -1
    best_score = -1.0
    for i, line in enumerate(lines):
        score = difflib.SequenceMatcher(None, line.strip(), target).ratio()
        if score > best_score:
            best_score = score
            best_i = i
    if best_i < 0 or best_score < 0.4:
        return ""
    start = max(0, best_i - radius)
    end = min(len(lines), best_i + radius + 1)
    return "\n".join(f"{idx + 1:>4}| {lines[idx]}" for idx in range(start, end))


def _commit_exact(content: str, old: str, new: str, count: int, replace_all: bool) -> str:
    if replace_all:
        return content.replace(old, new)
    if count > 1:
        raise ValueError(
            f"old_string appears {count} times; set replace_all=true or provide a unique snippet"
        )
    return content.replace(old, new, 1)


def _newline_style(content: str) -> tuple[str, str]:
    if "\r\n" in content:
        return content.replace("\r\n", "\n"), "\r\n"
    if "\r" in content and "\n" not in content:
        return content.replace("\r", "\n"), "\r"
    return content, "\n"


def _restore_newlines(text: str, newline: str) -> str:
    if newline == "\n":
        return text
    return text.replace("\n", newline)


def _line_spans(content: str) -> list[tuple[int, int, str]]:
    lines: list[tuple[int, int, str]] = []
    start = 0
    while start <= len(content):
        nl = content.find("\n", start)
        if nl == -1:
            lines.append((start, len(content), content[start:]))
            break
        lines.append((start, nl + 1, content[start:nl]))
        start = nl + 1
        if start == len(content):
            lines.append((start, start, ""))
            break
    return lines


def _norm_line(line: str, *, strip_indent: bool) -> str:
    text = line.expandtabs(4) if strip_indent else line
    text = text.rstrip()
    return text.lstrip() if strip_indent else text


def _collapse_ws(line: str) -> str:
    return " ".join(line.expandtabs(4).split())


def _span_end(content: str, file_lines: list[tuple[int, int, str]], last_index: int, old: str) -> int:
    end = file_lines[last_index][1]
    if not old.endswith("\n") and end > 0 and content[end - 1] == "\n":
        return end - 1
    return end


def _unique_ws_collapsed_span(content: str, old: str) -> tuple[int, int, str] | None:
    old_lines = old.split("\n")
    file_lines = _line_spans(content)
    n = len(old_lines)
    if n == 0 or n > len(file_lines):
        return None
    old_norm = [_collapse_ws(line) for line in old_lines]
    hits: list[tuple[int, int, str]] = []
    for i in range(len(file_lines) - n + 1):
        window = [_collapse_ws(file_lines[i + k][2]) for k in range(n)]
        if window != old_norm:
            continue
        start = file_lines[i][0]
        end = _span_end(content, file_lines, i + n - 1, old)
        hits.append((start, end, content[start:end]))
        if len(hits) > 1:
            return None
    return hits[0] if hits else None


def _unique_normalized_span(
    content: str,
    old: str,
    *,
    strip_indent: bool,
) -> tuple[int, int, str] | None:
    old_lines = old.split("\n")
    file_lines = _line_spans(content)
    n = len(old_lines)
    if n == 0 or n > len(file_lines):
        return None
    old_norm = [_norm_line(line, strip_indent=strip_indent) for line in old_lines]
    hits: list[tuple[int, int, str]] = []
    for i in range(len(file_lines) - n + 1):
        window = [_norm_line(file_lines[i + k][2], strip_indent=strip_indent) for k in range(n)]
        if window != old_norm:
            continue
        start = file_lines[i][0]
        end = _span_end(content, file_lines, i + n - 1, old)
        hits.append((start, end, content[start:end]))
        if len(hits) > 1:
            return None
    return hits[0] if hits else None


def _unique_anchor_span(content: str, old: str) -> tuple[int, int, str] | None:
    """Locate by first+last non-empty lines when the middle is slightly wrong."""
    old_lines = old.split("\n")
    nonempty = [(i, line) for i, line in enumerate(old_lines) if line.strip()]
    if len(nonempty) < 2:
        return None
    first_i, first = nonempty[0]
    last_i, last = nonempty[-1]
    n = len(old_lines)
    file_lines = _line_spans(content)
    if n > len(file_lines):
        return None
    first_key = _collapse_ws(first)
    last_key = _collapse_ws(last)
    hits: list[tuple[int, int, str]] = []
    for i in range(len(file_lines) - n + 1):
        head = _collapse_ws(file_lines[i + first_i][2])
        tail = _collapse_ws(file_lines[i + last_i][2])
        if head != first_key or tail != last_key:
            continue
        start = file_lines[i][0]
        end = _span_end(content, file_lines, i + n - 1, old)
        hits.append((start, end, content[start:end]))
        if len(hits) > 1:
            return None
    return hits[0] if hits else None


def _unique_suffix_span(content: str, old: str) -> tuple[int, int, str] | None:
    """Match old_string against the file tail (common for appending __main__)."""
    old_lines = old.split("\n")
    while old_lines and not old_lines[-1].strip():
        old_lines.pop()
    n = len(old_lines)
    if n == 0:
        return None
    file_lines = _line_spans(content)
    usable = list(file_lines)
    while usable and not usable[-1][2].strip() and len(usable) > 1:
        usable.pop()
    if n > len(usable):
        return None
    start_idx = len(usable) - n
    window = [_collapse_ws(usable[start_idx + k][2]) for k in range(n)]
    old_norm = [_collapse_ws(line) for line in old_lines]
    if window != old_norm:
        return None
    start = usable[start_idx][0]
    end = usable[start_idx + n - 1][1]
    if not old.endswith("\n") and end > 0 and content[end - 1] == "\n":
        end -= 1
    return start, end, content[start:end]


def _fuzzy_span(content: str, old: str) -> tuple[int, int, str] | None:
    old_lines = old.split("\n")
    file_lines = _line_spans(content)
    n = len(old_lines)
    if n == 0 or n > len(file_lines):
        return None
    old_blob = "\n".join(_norm_line(line, strip_indent=True) for line in old_lines)
    threshold = _FUZZY_RATIO_SHORT if n <= 3 else _FUZZY_RATIO
    scored: list[tuple[float, int, int]] = []
    for i in range(len(file_lines) - n + 1):
        window = "\n".join(_norm_line(file_lines[i + k][2], strip_indent=True) for k in range(n))
        ratio = difflib.SequenceMatcher(None, old_blob, window).ratio()
        if ratio < threshold:
            continue
        start = file_lines[i][0]
        end = _span_end(content, file_lines, i + n - 1, old)
        scored.append((ratio, start, end))
    if not scored:
        return None
    scored.sort(key=lambda item: -item[0])
    if len(scored) > 1 and scored[0][0] - scored[1][0] < _AMBIGUOUS_DELTA:
        return None
    _ratio, start, end = scored[0]
    return start, end, content[start:end]


def _leading_ws(line: str) -> str:
    index = 0
    while index < len(line) and line[index] in " \t":
        index += 1
    return line[:index]


def _align_indent(original: str, new: str) -> str:
    orig_lines = original.split("\n")
    new_lines = new.split("\n")
    if not orig_lines or not new_lines:
        return new
    orig_ws = _leading_ws(orig_lines[0])
    new_ws = _leading_ws(new_lines[0])
    if orig_ws == new_ws:
        return new
    out: list[str] = []
    for line in new_lines:
        if not line.strip():
            out.append(line)
            continue
        if new_ws and line.startswith(new_ws):
            out.append(orig_ws + line[len(new_ws) :])
        else:
            out.append(orig_ws + line.lstrip())
    return "\n".join(out)
