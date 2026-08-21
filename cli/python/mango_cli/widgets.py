from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import RichLog, Static, TextArea


def _short_path(path: str | Path, max_len: int = 48) -> str:
    text = str(path).replace("\\", "/")
    if len(text) <= max_len:
        return text
    return "…" + text[-(max_len - 1) :]


class MangoHeader(Static):
    """Single identity line: mango · workspace."""

    def set_workspace(self, workspace: str | Path) -> None:
        ws = _short_path(workspace)
        self.update(
            f"[bold #e8943a]mango[/] [#4a433c]·[/] [#a89f94]{ws}[/]"
        )


class TranscriptLog(RichLog):
    """Scrollable agent transcript — log lines, not cards."""

    DEFAULT_CSS = """
    TranscriptLog {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(markup=True, highlight=False, auto_scroll=True, **kwargs)

    def push_user(self, text: str) -> None:
        self.write(f"[#e8943a]>[/] {text.strip()}")

    def push_thought(self, text: str) -> None:
        body = text.strip()
        if not body:
            return
        # collapse to first meaningful chunk for console density
        lines = [ln.rstrip() for ln in body.splitlines() if ln.strip()]
        preview = lines[0] if lines else body
        if len(lines) > 1:
            preview = f"{preview} …"
        if len(preview) > 160:
            preview = preview[:157] + "…"
        self.write(f"[#7a7268]·[/] [#a89f94]{preview}[/]")

    def push_tool(self, title: str, *, ok: bool = True, blocked: bool = False) -> None:
        if blocked:
            self.write(f"[#e85d4c]![/] [#e85d4c]{title}[/] [#7a7268]blocked[/]")
        elif ok:
            self.write(f"[#e8943a]$[/] {title}")
        else:
            self.write(f"[#e85d4c]$[/] {title} [#7a7268]failed[/]")

    def push_file(self, path: str, *, action: str = "edited", added: int = 0, removed: int = 0) -> None:
        stats = ""
        if added or removed:
            stats = f"  [#3dba6e]+{added}[/] [#e8786e]-{removed}[/]"
        self.write(f"  [#7a7268]{action}[/] {path}{stats}")

    def push_verify(self, ok: bool, report: str = "") -> None:
        mark = "[#3dba6e]ok[/]" if ok else "[#e85d4c]fail[/]"
        line = f"[#7a7268]#[/] verify {mark}"
        if report.strip():
            snippet = report.strip().splitlines()[0][:100]
            line += f"  [#7a7268]{snippet}[/]"
        self.write(line)

    def push_final(self, text: str) -> None:
        body = text.strip()
        self.write(f"[#e8943a]✓[/] done")
        if body:
            for line in body.splitlines():
                self.write(f"  {line}")

    def push_error(self, text: str) -> None:
        self.write(f"[#e85d4c]x[/] {text.strip()}")

    def push_system(self, text: str) -> None:
        self.write(f"[#4a433c]#[/] [#7a7268]{text.strip()}[/]")


class ComposerInput(TextArea):
    """Goal input — looks like a shell prompt body."""

    BINDINGS = []


class MangoStatusBar(Static):
    status = reactive("ready")
    detail = reactive("")

    def render(self) -> str:
        if self.status == "running":
            head = "[#e8943a]…[/] [#e8943a]running[/]"
        elif self.status == "error":
            head = "[#e85d4c]x[/] [#e85d4c]error[/]"
        elif self.status == "ready" and self.detail and "iters" in self.detail:
            head = "[#3dba6e]·[/] [#3dba6e]ready[/]"
        else:
            head = "[#7a7268]·[/] ready"

        hint = "[#4a433c]  ^⏎ run  esc cancel[/]"
        tail = f"  [#7a7268]{self.detail}[/]" if self.detail else ""
        return f"{head}{tail}{hint}"

    def watch_status(self) -> None:
        self.refresh()

    def watch_detail(self) -> None:
        self.refresh()

    def set_running(self, detail: str = "") -> None:
        self.status = "running"
        self.detail = detail or "agent"

    def set_ready(self, detail: str = "") -> None:
        self.status = "ready"
        self.detail = detail

    def set_error(self, detail: str = "") -> None:
        self.status = "error"
        self.detail = detail
