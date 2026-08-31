"""Optional: start host when Roblox Studio process is detected."""

from __future__ import annotations

import subprocess
import sys
import time


def studio_running() -> bool:
    names = ("RobloxStudioBeta.exe", "RobloxStudio.exe")
    if sys.platform != "win32":
        # Best-effort: pgrep-like via ps
        try:
            out = subprocess.check_output(["ps", "-A", "-o", "comm="], text=True, errors="replace")
            return any("RobloxStudio" in line for line in out.splitlines())
        except Exception:
            return False
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq RobloxStudioBeta.exe", "/NH"],
            text=True,
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if "RobloxStudioBeta.exe" in out:
            return True
        out2 = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq RobloxStudio.exe", "/NH"],
            text=True,
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return "RobloxStudio.exe" in out2
    except Exception:
        return False


def watch_and_run(start_fn, *, poll_s: float = 5.0, stop_when_studio_exits: bool = False) -> None:
    """Call start_fn() once Studio is seen. start_fn should block (serve_forever)."""
    print("[mango-studio-host] waiting for Roblox Studio…", flush=True)
    while not studio_running():
        time.sleep(poll_s)
    print("[mango-studio-host] Studio detected — starting host", flush=True)
    start_fn()
