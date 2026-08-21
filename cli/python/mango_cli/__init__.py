"""Mango CLI — Textual terminal UI for Mango."""

__all__ = ["MangoApp"]

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mango_cli.app import MangoApp


def __getattr__(name: str):
    if name == "MangoApp":
        from mango_cli.app import MangoApp

        return MangoApp
    raise AttributeError(name)
