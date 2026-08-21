from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mango_cli.app import MangoApp
from mango_cli.paths import default_workspace, resolve_cli_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mango",
        description="Mango — local coding agent in the terminal",
    )
    parser.add_argument(
        "goal",
        nargs="?",
        default="",
        help="Optional goal; opens TUI and runs immediately when set",
    )
    parser.add_argument(
        "-w",
        "--workspace",
        type=Path,
        default=None,
        help="Project workspace (default: current directory)",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Config YAML (default: <workspace>/.mango/config.yaml, auto-created)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = (args.workspace or default_workspace()).resolve()
    config = resolve_cli_config(workspace, args.config)

    if not config.is_file():
        print(f"mango: could not create config: {config}", file=sys.stderr)
        return 1

    app = MangoApp(
        workspace=workspace,
        config_path=config,
        initial_goal=args.goal,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
