from __future__ import annotations

from pathlib import Path

from textual import events
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import RichLog, Static, TextArea

from mango_cli.commands import SLASH_COLORS


def short_path(path: str | Path, max_len: int = 52) -> str:
    text = str(path).replace("\\", "/")
    if len(text) <= max_len:
        return text
    return "…" + text[-(max_len - 1) :]


class MangoHeader(Static):
    mode = reactive("agent")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._workspace = ""
        self._model = ""

    def set_workspace(self, workspace: str | Path) -> None:
        self._workspace = short_path(workspace)
        self._redraw()

    def set_model(self, model: str) -> None:
        name = Path(model).name if model else ""
        if name.endswith(".gguf"):
            name = name[:-5]
        self._model = name[:36]
        self._redraw()

    def set_mode(self, mode: str) -> None:
        self.mode = (mode or "agent").strip().lower() or "agent"

    def watch_mode(self) -> None:
        self._redraw()

    def _redraw(self) -> None:
        color = SLASH_COLORS.get(self.mode, "#e8943a")
        model = self._model or "local"
        ws = self._workspace or "."
        self.update(
            f"[bold #e8943a]mango[/] [#4a433c]·[/] [#a89f94]{ws}[/] "
            f"[#4a433c]·[/] [{color}]{self.mode}[/] [#4a433c]·[/] [#7a7268]{model}[/]"
        )


class TranscriptLog(RichLog):
    DEFAULT_CSS = """
    TranscriptLog { height: 1fr; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(markup=True, highlight=False, auto_scroll=True, wrap=True, **kwargs)

    def push_banner(self, workspace: str, model: str = "") -> None:
        ws = short_path(workspace, 64)
        model_line = f"  [#7a7268]model[/]   [#a89f94]{model}[/]\n" if model else ""
        self.write(
            "[#e8943a]╭ mango[/] [#4a433c]───────────────────────────────────────[/]\n"
            f"  [#7a7268]cwd[/]     [#a89f94]{ws}[/]\n"
            f"{model_line}"
            "  [#7a7268]hint[/]    [#a89f94]/help · /ask · /plan · /debug · /refactor[/]\n"
            "[#e8943a]╰[/] [#4a433c]type a goal or /command — ⏎ send · ⇧⏎ newline[/]"
        )

    def push_user(self, text: str, *, mode: str = "") -> None:
        color = SLASH_COLORS.get(mode, "#e8943a") if mode else "#e8943a"
        label = mode or "you"
        self.write("")
        self.write(f"[{color}]❯[/] [bold {color}]{label}[/] [#4a433c]──[/]")
        for line in text.strip().splitlines() or [""]:
            self.write(f"  {line}")

    def push_thought(self, text: str) -> None:
        body = text.strip()
        if not body:
            return
        lines = [ln.rstrip() for ln in body.splitlines() if ln.strip()]
        preview = lines[0] if lines else body
        if len(lines) > 1:
            preview = f"{preview} …"
        if len(preview) > 140:
            preview = preview[:137] + "…"
        self.write(f"  [#4a433c]thinking[/]  [#7a7268]{preview}[/]")

    def push_tool(self, title: str, *, ok: bool = True, blocked: bool = False) -> None:
        if blocked:
            self.write(f"  [#e85d4c]✗[/] [#e85d4c]{title}[/] [#7a7268]blocked[/]")
        elif ok:
            self.write(f"  [#e8943a]●[/] [#f5f2ed]{title}[/]")
        else:
            self.write(f"  [#e85d4c]●[/] [#e85d4c]{title}[/] [#7a7268]failed[/]")

    def push_file(
        self,
        path: str,
        *,
        action: str = "edited",
        added: int = 0,
        removed: int = 0,
    ) -> None:
        stats = ""
        if added or removed:
            stats = f"  [#3dba6e]+{added}[/] [#e8786e]-{removed}[/]"
        self.write(f"    [#7a7268]{action}[/] [#a89f94]{path}[/]{stats}")

    def push_verify(self, ok: bool, report: str = "") -> None:
        mark = "[#3dba6e]ok[/]" if ok else "[#e85d4c]fail[/]"
        line = f"  [#7a7268]verify[/] {mark}"
        if report.strip():
            snippet = report.strip().splitlines()[0][:100]
            line += f"  [#7a7268]{snippet}[/]"
        self.write(line)

    def push_final(self, text: str) -> None:
        body = text.strip()
        self.write("  [#3dba6e]✓[/] [#3dba6e]done[/]")
        if body:
            self.write("  [#4a433c]── answer ──────────────────────────[/]")
            for line in body.splitlines():
                self.write(f"  {line}")

    def push_error(self, text: str) -> None:
        self.write(f"  [#e85d4c]✗[/] {text.strip()}")

    def push_system(self, text: str) -> None:
        self.write(f"[#4a433c]#[/] [#7a7268]{text.strip()}[/]")

    def push_markup(self, markup: str) -> None:
        self.write(markup)


class ComposerInput(TextArea):
    """Multiline goal input — Enter sends; Shift+Enter inserts a newline."""

    BINDINGS: list = []

    class Submitted(Message):
        """User pressed Enter to submit the composer."""

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.post_message(self.Submitted())
            return
        if event.key == "shift+enter":
            event.prevent_default()
            event.stop()
            self.insert("\n")
            return
        await super()._on_key(event)


class MangoStatusBar(Static):
    status = reactive("ready")
    detail = reactive("")
    mode = reactive("agent")

    def render(self) -> str:
        color = SLASH_COLORS.get(self.mode, "#e8943a")
        if self.status == "running":
            head = f"[{color}]…[/] [{color}]running[/]"
        elif self.status == "error":
            head = "[#e85d4c]✗[/] [#e85d4c]error[/]"
        elif self.status == "ready" and self.detail and "iters" in self.detail:
            head = "[#3dba6e]·[/] [#3dba6e]ready[/]"
        else:
            head = "[#7a7268]·[/] ready"
        mode = f"  [{color}]/{self.mode}[/]" if self.mode and self.mode != "agent" else ""
        hint = "  [#4a433c]⏎ send  ⇧⏎ newline  esc cancel  /help[/]"
        tail = f"  [#7a7268]{self.detail}[/]" if self.detail else ""
        return f"{head}{mode}{tail}{hint}"

    def watch_status(self) -> None:
        self.refresh()

    def watch_detail(self) -> None:
        self.refresh()

    def watch_mode(self) -> None:
        self.refresh()

    def set_running(self, detail: str = "", *, mode: str = "") -> None:
        if mode:
            self.mode = mode
        self.status = "running"
        self.detail = detail or "agent"

    def set_ready(self, detail: str = "") -> None:
        self.status = "ready"
        self.detail = detail

    def set_error(self, detail: str = "") -> None:
        self.status = "error"
        self.detail = detail

    def set_mode(self, mode: str) -> None:
        self.mode = (mode or "agent").strip().lower() or "agent"
