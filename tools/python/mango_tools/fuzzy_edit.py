from __future__ import annotations

import difflib

_FUZZY_RATIO = 0.86
_AMBIGUOUS_DELTA = 0.04
_UNCHANGED = "file unchanged; tests still fail; change the implementation"


def apply_replace(
    content: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
    allow_fuzzy: bool = True,
) -> tuple[str, int, str]:
    """Replace old_string in content. Returns (updated, count, match_kind)."""
    if old_string == new_string:
        raise ValueError(_UNCHANGED)
    if not old_string:
        raise ValueError("old_string is empty")

    count = content.count(old_string)
    if count:
        return _commit_exact(content, old_string, new_string, count, replace_all), count if replace_all else 1, "exact"

    normalized, newline = _newline_style(content)
    old_n = old_string.replace("\r\n", "\n").replace("\r", "\n")
    new_n = new_string.replace("\r\n", "\n").replace("\r", "\n")
    count = normalized.count(old_n)
    if count:
        updated = _commit_exact(normalized, old_n, new_n, count, replace_all)
        n = count if replace_all else 1
        return _restore_newlines(updated, newline), n, "newlines"

    if not allow_fuzzy:
        raise ValueError(
            "old_string not found in file. read_file first and copy old_string exactly "
            "(no fuzzy/whitespace match)."
        )

    span = _unique_normalized_span(normalized, old_n, strip_indent=False)
    if span is not None:
        start, end, _original = span
        updated = normalized[:start] + new_n + normalized[end:]
        return _restore_newlines(updated, newline), 1, "whitespace"

    span = _unique_normalized_span(normalized, old_n, strip_indent=True)
    if span is not None:
        start, end, original = span
        updated = normalized[:start] + _align_indent(original, new_n) + normalized[end:]
        return _restore_newlines(updated, newline), 1, "indent"

    span = _fuzzy_span(normalized, old_n)
    if span is not None:
        start, end, original = span
        updated = normalized[:start] + _align_indent(original, new_n) + normalized[end:]
        return _restore_newlines(updated, newline), 1, "fuzzy"

    raise ValueError(
        "old_string not found in file. Copy a unique snippet from the file, "
        "or call write_file with the complete file contents."
    )


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
    """(start, end_exclusive, line_without_newline) for each line."""
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


def _span_end(content: str, file_lines: list[tuple[int, int, str]], last_index: int, old: str) -> int:
    end = file_lines[last_index][1]
    if not old.endswith("\n") and end > 0 and content[end - 1] == "\n":
        return end - 1
    return end


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


def _fuzzy_span(content: str, old: str) -> tuple[int, int, str] | None:
    old_lines = old.split("\n")
    file_lines = _line_spans(content)
    n = len(old_lines)
    if n == 0 or n > len(file_lines):
        return None
    old_blob = "\n".join(_norm_line(line, strip_indent=True) for line in old_lines)
    scored: list[tuple[float, int, int]] = []
    for i in range(len(file_lines) - n + 1):
        window = "\n".join(_norm_line(file_lines[i + k][2], strip_indent=True) for k in range(n))
        ratio = difflib.SequenceMatcher(None, old_blob, window).ratio()
        if ratio < _FUZZY_RATIO:
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
