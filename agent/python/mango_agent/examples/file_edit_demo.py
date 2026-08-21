"""Run the file-edit demo: python -m mango_agent.examples.file_edit_demo"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from mango_agent import Agent, StopReason, create_agent


def run_demo(*, config: str | None = None, max_iterations: int = 8) -> int:
    with tempfile.TemporaryDirectory(prefix="mango-agent-demo-") as tmp:
        sample_file = Path(tmp) / "greeting.txt"
        sample_file.write_text("Hello Mango\n", encoding="utf-8")

        task = (
            f'File path: "{sample_file}"\n'
            f'1) read_file that path\n'
            f'2) edit_file: replace "Mango" with "Agent"\n'
            f'3) read_file again and report the final content'
        )

        print("=== Mango Agent Demo ===", file=sys.stderr)
        print(f"Sample file: {sample_file}", file=sys.stderr)
        print(f"Initial content: {sample_file.read_text(encoding='utf-8')!r}", file=sys.stderr)
        print(f"Task: {task}\n", file=sys.stderr)

        agent = create_agent(runtime_config=config, max_iterations=max_iterations, max_tokens=512)
        try:
            result = agent.run(task)
        finally:
            agent.close()

        print("=== Agent Trace ===", file=sys.stderr)
        for step in result.steps:
            print(f"\n--- Iteration {step.iteration} ---", file=sys.stderr)
            print(step.model_output, file=sys.stderr)
            for tool_result in step.tool_results:
                print(
                    f"Tool {tool_result.tool_name}: success={tool_result.success}",
                    file=sys.stderr,
                )

        print("\n=== Final Answer ===", file=sys.stderr)
        print(result.final_answer)
        print(f"\nStop reason: {result.stop_reason.value}", file=sys.stderr)
        print(f"On-disk content: {sample_file.read_text(encoding='utf-8')!r}", file=sys.stderr)

        if result.stop_reason != StopReason.COMPLETED:
            return 1
        if "Agent" not in sample_file.read_text(encoding="utf-8"):
            print("Expected file content to contain 'Agent'.", file=sys.stderr)
            return 1
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mango file-edit agent demo")
    parser.add_argument("--config", help="Path to runtime config.yaml")
    parser.add_argument("--max-iterations", type=int, default=8)
    args = parser.parse_args(argv)
    return run_demo(config=args.config, max_iterations=args.max_iterations)


if __name__ == "__main__":
    raise SystemExit(main())
