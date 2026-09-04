"""Structured debug logger — never raises."""

from __future__ import annotations

import sys
from typing import Any


def debug(scope: str, message: str, detail: Any = None) -> None:
    try:
        line = f"[mango:{scope}] {message}"
        if detail is not None:
            print(line, detail, file=sys.stderr, flush=True)
        else:
            print(line, file=sys.stderr, flush=True)
    except Exception:
        pass
