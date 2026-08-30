"""Windows-safe entry for the official SWE-bench Docker harness.

On Windows, ``Path.write_text`` defaults to CRLF. The harness writes ``patch.diff``
and ``eval.sh`` that way, which breaks ``git apply`` / bash inside Linux containers
(``set: pipefail\\r: invalid option name``). Writing ``test_output.txt`` in text mode
also hits cp1252 UnicodeEncodeError on some instances.

Run this as ``python -m mango_agent.benchmark.swebench.harness_winfix`` with the same
CLI flags as ``swebench.harness.run_evaluation``.
"""

from __future__ import annotations

import builtins
import pathlib
import runpy
import sys


def apply_windows_harness_fixes() -> None:
    """Force LF for harness scripts/patches and UTF-8 for test_output.txt."""
    if sys.platform != "win32":
        return

    _orig_write_text = pathlib.Path.write_text

    def write_text(self: pathlib.Path, data, encoding=None, errors=None, newline=None):  # type: ignore[no-untyped-def]
        name = self.name.lower()
        if name in {"patch.diff", "eval.sh"} or self.suffix.lower() in {".diff", ".sh"}:
            newline = "\n"
            if isinstance(data, str):
                data = data.replace("\r\n", "\n").replace("\r", "\n")
        return _orig_write_text(
            self, data, encoding=encoding, errors=errors, newline=newline
        )

    pathlib.Path.write_text = write_text  # type: ignore[method-assign]

    _orig_open = builtins.open

    def open_utf8(file, mode="r", *args, **kwargs):  # type: ignore[no-untyped-def]
        path_s = str(file).replace("\\", "/")
        if "w" in str(mode) and path_s.endswith("test_output.txt"):
            kwargs.setdefault("encoding", "utf-8")
            kwargs.setdefault("errors", "replace")
        return _orig_open(file, mode, *args, **kwargs)

    builtins.open = open_utf8  # type: ignore[assignment]


def main() -> None:
    apply_windows_harness_fixes()
    runpy.run_module(
        "swebench.harness.run_evaluation",
        run_name="__main__",
        alter_sys=True,
    )


if __name__ == "__main__":
    main()
