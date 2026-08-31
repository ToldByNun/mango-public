"""CLI entry: python -m mango_studio_host [--port 17880] [--wait-for-studio]."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mango Studio Host (Roblox plugin bridge)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=17880, help="HTTP port (default 17880)")
    parser.add_argument(
        "--wait-for-studio",
        action="store_true",
        help="Delay listen until Roblox Studio process is detected",
    )
    args = parser.parse_args(argv)

    from mango_studio_host.http_server import serve_forever

    def start() -> None:
        serve_forever(host=args.host, port=args.port)

    if args.wait_for_studio:
        from mango_studio_host.autostart import watch_and_run

        watch_and_run(start)
    else:
        start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
