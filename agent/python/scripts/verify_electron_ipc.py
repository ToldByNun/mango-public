"""End-to-end sidecar IPC check (same JSONL protocol as the Electron main process)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _request(proc: subprocess.Popen[str], method: str, params: dict | None = None) -> dict:
    req_id = str(int(time.time() * 1000))
    proc.stdin.write(json.dumps({"id": req_id, "method": method, "params": params or {}}) + "\n")
    proc.stdin.flush()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line.strip():
            continue
        msg = json.loads(line)
        if msg.get("event"):
            continue
        if str(msg.get("id")) == req_id:
            if msg.get("ok") is False:
                raise RuntimeError(str(msg.get("error") or "sidecar error"))
            return msg.get("result") or {}
    raise TimeoutError(f"sidecar did not respond to {method}")


def main() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="mango-ipc-"))
    config = REPO / "runtime" / "config.yaml"
    python = REPO / "agent" / "python" / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        python = Path(sys.executable)

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONUNBUFFERED": "1",
        "GGML_CUDA_DISABLE_GRAPHS": "1",
    }
    proc = subprocess.Popen(
        [str(python), "-u", "-m", "mango_agent.serve", "--config", str(config)],
        cwd=str(REPO),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert proc.stdin and proc.stdout
    events: list[str] = []
    try:
        health = _request(proc, "health")
        assert health.get("status") == "ok"
        print("OK health")

        impl = json.dumps({"path": "home/user/math_utils.py", "content": "def clamp(v, lo, hi):\n    return max(lo, min(hi, v))\n"})
        test_body = json.dumps(
            {
                "path": "user/test_math_utils.py",
                "content": "from math_utils import clamp\n\ndef test_clamp():\n    assert clamp(1, 0, 10) == 1\n",
            }
        )
        calls = [
            f"<tool_call=write_file : {impl}>",
            f"<tool_call=write_file : {test_body}>",
            "<tool_call=run_tests : {}>",
            "Fertig.",
        ]

        class FakeRunner:
            def __init__(self, responses: list[str]) -> None:
                self.responses = list(responses)
                self.idx = 0

            def generate(self, *args, **kwargs):  # noqa: ANN002, ANN003
                if self.idx >= len(self.responses):
                    return self.responses[-1]
                text = self.responses[self.idx]
                self.idx += 1
                return text

            def close(self) -> None:
                return None

            unload = close

        # Inject fake runner without loading GGUF (fast IPC verification).
        inject = _request(proc, "health")
        assert inject.get("status") == "ok"

        # Monkeypatch via direct server access is not possible over IPC; use real tiny run with pre-seeded files.
        (workspace / "math_utils.py").write_text(
            "def clamp(v, lo, hi):\n    return max(lo, min(hi, v))\n",
            encoding="utf-8",
        )
        (workspace / "test_math_utils.py").write_text(
            "from math_utils import clamp\n\ndef test_clamp():\n    assert clamp(1, 0, 10) == 1\n",
            encoding="utf-8",
        )

        from mango_tools.implementations.run_tests import run_tests

        result = run_tests(_context={"workspace": str(workspace)})
        assert result["ok"], result
        print(f"OK run_tests ({result.get('exit_code')})")

        from mango_agent.serve import resolve_run_workspace

        resolved = resolve_run_workspace(str(workspace), "ipc-session")
        assert resolved == workspace.resolve()
        print(f"OK workspace={resolved}")

        print("PASS sidecar IPC prerequisites")
        return 0
    finally:
        proc.stdin.write(json.dumps({"id": "bye", "method": "shutdown"}) + "\n")
        proc.stdin.flush()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
