"""In-process studio dispatch used by rbx_* tools inside the sidecar.

When MANGO_STUDIO_BRIDGE_URL is set (host injects this), tools POST here and
block until the Studio plugin completes the call via the host queue.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def studio_bridge_url() -> str:
    return (os.environ.get("MANGO_STUDIO_BRIDGE_URL") or "").strip().rstrip("/")


def studio_dispatch_available() -> bool:
    return bool(studio_bridge_url())


def dispatch_studio_tool(
    tool: str,
    args: dict[str, Any],
    *,
    requires_confirm: bool = False,
    confirm_summary: str = "",
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """POST a studio tool call to the host bridge and return the plugin result."""
    base = studio_bridge_url()
    if not base:
        return {
            "ok": False,
            "error": "studio_bridge_unavailable",
            "detail": "MANGO_STUDIO_BRIDGE_URL is not set — start mango-studio-host",
        }
    body = {
        "tool": tool,
        "args": args or {},
        "requires_confirm": requires_confirm,
        "confirm_summary": confirm_summary or "",
    }
    if timeout_s is not None:
        body["timeout_s"] = timeout_s
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/internal/studio/call",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Confirm calls can wait up to ~120s+; urllib timeout must cover that.
    http_timeout = float(timeout_s) if timeout_s is not None else (130.0 if requires_confirm else 70.0)
    try:
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            if isinstance(parsed, dict):
                return parsed
            return {"ok": False, "error": "bad_bridge_response", "detail": str(parsed)}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        return {"ok": False, "error": "bridge_http_error", "detail": detail}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "bridge_error", "detail": str(exc)}
