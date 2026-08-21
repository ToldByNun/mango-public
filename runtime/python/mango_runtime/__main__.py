"""CLI smoke entry: python -m mango_runtime "Your prompt here"."""

from __future__ import annotations

import argparse
import sys

from mango_runtime.model_runner import ModelRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mango GGUF model runner")
    parser.add_argument("prompt", nargs="?", default="Hello! Reply in one short sentence.")
    parser.add_argument("--config", help="Path to runtime config.yaml")
    parser.add_argument("--stream", action="store_true", help="Stream tokens to stdout")
    args = parser.parse_args(argv)

    runner = ModelRunner(args.config)
    print(f"Loading model: {runner.config.model.path}", file=sys.stderr)

    with runner:
        if args.stream:
            for token in runner.complete_stream(args.prompt):
                print(token, end="", flush=True)
            print()
            print("\n[stream complete]", file=sys.stderr)
        else:
            result = runner.complete(args.prompt)
            print(result.text)
            print(f"\n[{result.completion_tokens} completion tokens]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
