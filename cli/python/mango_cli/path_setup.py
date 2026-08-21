from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__).resolve()).expanduser()
    if here.is_file():
        here = here.parent
    for candidate in (here, *here.parents):
        if (candidate / "agent" / "python").is_dir() and (candidate / "runtime").is_dir():
            return candidate.resolve()
    return here.resolve()


def bin_directory(start: Path | None = None) -> Path:
    return repo_root(start) / "bin"


def venv_scripts(start: Path | None = None) -> Path:
    root = repo_root(start)
    win = root / "agent" / "python" / ".venv" / "Scripts"
    if win.is_dir():
        return win
    return root / "agent" / "python" / ".venv" / "bin"


def _split_path(value: str) -> list[str]:
    parts = value.split(os.pathsep)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = part.strip().strip('"')
        if not text:
            continue
        key = text.rstrip("\\/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _path_contains(path_list: list[str], target: str) -> bool:
    key = target.rstrip("\\/").lower()
    return any(item.rstrip("\\/").lower() == key for item in path_list)


def _broadcast_windows_env_change() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            None,
        )
    except Exception:
        pass


def ensure_user_path(*entries: str | Path) -> list[str]:
    """Append missing directories to the user PATH. Returns newly added entries."""
    targets = [str(Path(item).expanduser().resolve()) for item in entries if str(item).strip()]
    if not targets:
        return []

    if sys.platform == "win32":
        user_current = _read_windows_user_path()
        merged = _split_path(user_current)
        added: list[str] = []
        for target in targets:
            if _path_contains(merged, target):
                continue
            merged.append(target)
            added.append(target)
        if not added:
            return []
        new_value = os.pathsep.join(merged)
        _write_windows_user_path(new_value)
        process_parts = _split_path(os.environ.get("Path", ""))
        for target in added:
            if not _path_contains(process_parts, target):
                process_parts.insert(0, target)
        os.environ["Path"] = os.pathsep.join(process_parts)
        _broadcast_windows_env_change()
        return added

    home = Path.home()
    profile = home / ".profile"
    if not profile.is_file():
        profile = home / ".bashrc"
    export_lines = []
    for target in targets:
        export_lines.append(f'export PATH="{target}:$PATH"  # mango')
    marker = "# mango-path"
    text = profile.read_text(encoding="utf-8") if profile.is_file() else ""
    if marker in text:
        return []
    profile.parent.mkdir(parents=True, exist_ok=True)
    with profile.open("a", encoding="utf-8") as handle:
        handle.write(f"\n{marker}\n")
        handle.write("\n".join(export_lines) + "\n")
    return targets


def ensure_mango_path(start: Path | None = None) -> list[str]:
    """Register mango launchers on user PATH."""
    root = repo_root(start)
    bindir = bin_directory(root)
    bindir.mkdir(parents=True, exist_ok=True)
    scripts = venv_scripts(root)
    entries = [bindir]
    if scripts.is_dir():
        entries.append(scripts)
    return ensure_user_path(*entries)


def _read_windows_user_path() -> str:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
        try:
            value, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            return ""
    return str(value or "")


def _write_windows_user_path(value: str) -> None:
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Environment",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, value)


def main() -> int:
    added = ensure_mango_path()
    if added:
        print("Added to user PATH:")
        for item in added:
            print(f"  {item}")
        print("Open a new terminal, then run: mango")
    else:
        bindir = bin_directory()
        scripts = venv_scripts()
        print("User PATH already has mango launchers:")
        print(f"  {bindir}")
        if scripts.is_dir():
            print(f"  {scripts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
