from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mango_tools.implementations.runtime_smoke import discover_entry_scripts, run_runtime_smoke


def test_discover_entry_scripts_skips_tests(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        "def main():\n    pass\n\nif __name__ == '__main__':\n    main()\n",
        encoding="utf-8",
    )
    (tmp_path / "test_app.py").write_text(
        "def test_x():\n    assert True\n",
        encoding="utf-8",
    )
    found = discover_entry_scripts(tmp_path)
    assert len(found) == 1
    assert found[0].endswith("app.py")


def test_runtime_smoke_catches_crash(tmp_path: Path) -> None:
    script = tmp_path / "boom.py"
    script.write_text(
        textwrap.dedent(
            """
            def main():
                hh = 0
                _ = str(hh)[1]

            if __name__ == "__main__":
                main()
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    result = run_runtime_smoke(_context={"workspace": str(tmp_path)})
    assert result["ok"] is False
    assert "Traceback" in str(result.get("detail") or "")


def test_runtime_smoke_passes_clean_script(tmp_path: Path) -> None:
    script = tmp_path / "ok.py"
    script.write_text(
        "if __name__ == '__main__':\n    print('hi')\n",
        encoding="utf-8",
    )
    result = run_runtime_smoke(_context={"workspace": str(tmp_path)})
    assert result["ok"] is True


def test_runtime_smoke_allows_long_running_without_traceback(tmp_path: Path) -> None:
    script = tmp_path / "loop.py"
    script.write_text(
        "if __name__ == '__main__':\n    import time\n    time.sleep(60)\n",
        encoding="utf-8",
    )
    result = run_runtime_smoke(_context={"workspace": str(tmp_path)}, timeout=1)
    assert result["ok"] is True
    assert result["results"][0]["timed_out"] is True
