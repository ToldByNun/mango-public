from __future__ import annotations

import subprocess
from pathlib import Path

from mango_codeintel.types import GitSnapshot


def git_snapshot(root: Path) -> GitSnapshot:
    if not (root / ".git").exists():
        return GitSnapshot(available=False)
    branch = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    status = _git(root, ["status", "--porcelain"])
    log = _git(root, ["log", "-5", "--oneline"])
    changed = []
    for line in status.splitlines():
        path = line[3:].strip() if len(line) > 3 else ""
        if path:
            changed.append(path.replace("\\", "/"))
    commits = [line.strip() for line in log.splitlines() if line.strip()]
    return GitSnapshot(
        branch=branch.strip(),
        changed_files=changed,
        recent_commits=commits,
        available=True,
    )


def _git(root: Path, args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout
