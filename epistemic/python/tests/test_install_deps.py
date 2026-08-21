from __future__ import annotations

from mango_epistemic.install_deps import (
    can_import,
    ensure_packages,
    missing_import_roots,
    resolve_pip_name,
)
from mango_epistemic.targets import lookup_targets


def test_resolve_pip_name_discord() -> None:
    assert resolve_pip_name("discord") == "discord.py"
    assert resolve_pip_name("discord.ext.commands") == "discord.py"


def test_resolve_pip_name_skips_stdlib_and_noise() -> None:
    assert resolve_pip_name("json") is None
    assert resolve_pip_name("commands") is None
    assert resolve_pip_name("threading") is None


def test_ensure_packages_noop_when_importable() -> None:
    result = ensure_packages(["json"])
    assert result["ok"] is True
    assert result["command"] is None
    assert result["installed"] == []


def test_missing_import_roots_from_cards() -> None:
    cards = [
        {
            "exists": False,
            "package": "discord",
            "error": "import failed: No module named 'discord'",
        },
        {
            "exists": False,
            "package": "commands",
            "error": "import failed: No module named 'commands'",
        },
    ]
    roots = missing_import_roots(cards)
    assert roots == ["discord", "commands"]
    # commands is skipped at resolve time
    assert resolve_pip_name("commands") is None
    assert can_import("json") is True


def test_lookup_targets_discord_not_bare_commands() -> None:
    targets = lookup_targets("discord.py Bot commands Client")
    packages = {pkg for pkg, _ in targets}
    assert "discord" in packages or any(pkg.startswith("discord") for pkg in packages)
    assert ("commands", "Bot") not in targets
    assert all(pkg != "commands" for pkg, _ in targets)
    assert ("discord", "py") not in targets


def test_lookup_targets_discord_py_not_symbol_py() -> None:
    targets = lookup_targets("How do I use discord.py Client and Bot?")
    assert ("discord", "py") not in targets
    assert any(pkg == "discord" or pkg.startswith("discord.") for pkg, _ in targets)
