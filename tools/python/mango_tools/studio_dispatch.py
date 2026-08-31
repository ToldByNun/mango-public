"""HTTP dispatch from sidecar rbx_* tools to mango-studio-host."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def studio_bridge_url() -> str:
    return (os.environ.get("MANGO_STUDIO_BRIDGE_URL") or "").strip().rstrip("/")


def dispatch_studio_tool(
    tool: str,
    args: dict[str, Any],
    *,
    requires_confirm: bool = False,
    confirm_summary: str = "",
    timeout_s: float | None = None,
) -> dict[str, Any]:
    base = studio_bridge_url()
    if not base:
        return {
            "ok": False,
            "error": "studio_bridge_unavailable",
            "detail": "MANGO_STUDIO_BRIDGE_URL is not set — start mango-studio-host",
        }
    body: dict[str, Any] = {
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
    http_timeout = float(timeout_s) if timeout_s is not None else (130.0 if requires_confirm else 70.0)
    try:
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return parsed if isinstance(parsed, dict) else {"ok": False, "error": "bad_response"}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        return {"ok": False, "error": "bridge_http_error", "detail": detail}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "bridge_error", "detail": str(exc)}
