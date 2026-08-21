from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
from typing import Any

# Import-root → PyPI distribution name (when they differ).
_PIP_ALIASES: dict[str, str] = {
    "discord": "discord.py",
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "pil": "Pillow",
    "pillow": "Pillow",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "beautifulsoup": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "serial": "pyserial",
    "usb": "pyusb",
    "gi": "PyGObject",
    "wx": "wxPython",
    "attr": "attrs",
    "skimage": "scikit-image",
    "torchvision": "torchvision",
    "torchaudio": "torchaudio",
}

# Bare words that look like packages but are usually nested modules / false positives.
_SKIP_INSTALL = frozenset(
    {
        "commands",
        "ext",
        "utils",
        "helpers",
        "tests",
        "test",
        "src",
        "lib",
        "core",
        "api",
        "client",
        "server",
        "bot",
        "models",
        "views",
        "types",
        "config",
        "main",
        "app",
    }
)


def _stdlib_names() -> frozenset[str]:
    names = set(getattr(sys, "stdlib_module_names", ()) or ())
    names.update({"__future__", "builtins", "sitecustomize", "usercustomize"})
    return frozenset(names)


def can_import(name: str) -> bool:
    root = str(name or "").split(".", 1)[0].strip()
    if not root:
        return False
    try:
        return importlib.util.find_spec(root) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def resolve_pip_name(import_name: str) -> str | None:
    """Return a PyPI package to install for this import, or None if we must not install."""
    root = str(import_name or "").split(".", 1)[0].strip()
    if not root:
        return None
    key = root.lower()
    if key in _SKIP_INSTALL:
        return None
    if key in _stdlib_names():
        return None
    return _PIP_ALIASES.get(key, root)


def ensure_packages(
    import_names: list[str],
    *,
    timeout: int = 180,
    python: str | None = None,
) -> dict[str, Any]:
    """Install missing third-party packages via ``python -m pip install``.

    Returns a structured result suitable for tool UI / epistemic cards.
    """
    wanted: list[str] = []
    skipped: list[str] = []
    already: list[str] = []
    for raw in import_names:
        root = str(raw or "").split(".", 1)[0].strip()
        if not root:
            continue
        pip_name = resolve_pip_name(root)
        if pip_name is None:
            skipped.append(root)
            continue
        if can_import(root):
            already.append(root)
            continue
        if pip_name not in wanted:
            wanted.append(pip_name)

    if not wanted:
        return {
            "ok": True,
            "installed": [],
            "already": already,
            "skipped": skipped,
            "command": None,
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        }

    exe = python or sys.executable
    command = f'"{exe}" -m pip install {" ".join(wanted)}'
    argv = [exe, "-m", "pip", "install", *wanted]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=flags,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        code = int(proc.returncode)
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = f"pip install timed out after {timeout}s"
        code = -1
    except OSError as exc:
        stdout = ""
        stderr = str(exc)
        code = -1

    importlib.invalidate_caches()
    # Drop cached failed imports so can_import/find_spec sees the new install.
    for pip_name in wanted:
        root = _import_root_for_pip(pip_name)
        sys.modules.pop(root, None)

    installed: list[str] = []
    failed: list[str] = []
    for pip_name in wanted:
        root = _import_root_for_pip(pip_name)
        if code == 0 and can_import(root):
            installed.append(pip_name)
        else:
            failed.append(pip_name)

    return {
        "ok": code == 0 and not failed,
        "installed": installed,
        "failed": failed,
        "already": already,
        "skipped": skipped,
        "command": command,
        "stdout": stdout[-4_000:],
        "stderr": stderr[-4_000:],
        "exit_code": code,
    }


def _import_root_for_pip(pip_name: str) -> str:
    """Best-effort reverse map for post-install import checks."""
    low = pip_name.lower()
    for import_name, dist in _PIP_ALIASES.items():
        if dist.lower() == low:
            return import_name
    # discord.py → try discord
    if low.endswith(".py"):
        return low[: -len(".py")]
    if "-" in pip_name:
        return pip_name.split("-", 1)[0]
    return pip_name


def missing_import_roots(cards: list[dict[str, Any]]) -> list[str]:
    """Collect import roots from failed inspect cards."""
    roots: list[str] = []
    seen: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        if card.get("exists") is not False:
            continue
        err = str(card.get("error") or "").lower()
        if "import failed" not in err and "no module named" not in err:
            continue
        pkg = str(card.get("package") or card.get("library") or "").strip()
        root = pkg.split(".", 1)[0].strip()
        if not root or root.lower() in seen:
            continue
        seen.add(root.lower())
        roots.append(root)
    return roots
