from __future__ import annotations

from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from mango_cli.agent_bridge import AgentBridge
from mango_cli.commands import SLASH_COLORS, help_text, parse_slash
from mango_cli.paths import default_workspace, resolve_cli_config
from mango_cli.widgets import ComposerInput, MangoHeader, MangoStatusBar, TranscriptLog, short_path


class MangoApp(App):
    """Terminal-first Mango — structured like Aider / Claude Code."""

    CSS_PATH = "theme.tcss"
    TITLE = "mango"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+enter", "submit_goal", "Run", show=False),
        Binding("ctrl+j", "submit_goal", "Run", show=False),
        Binding("ctrl+l", "clear_transcript", "Clear", show=False),
        Binding("escape", "cancel_run", "Cancel", show=False),
        Binding("ctrl+c", "cancel_or_quit", "Cancel/Quit", show=False),
    ]

    def __init__(
        self,
        *,
        workspace: Path | None = None,
        config_path: Path | None = None,
        initial_goal: str = "",
    ) -> None:
        super().__init__()
        self._workspace = workspace or default_workspace()
        self._config = config_path or resolve_cli_config(self._workspace)
        self._initial_goal = initial_goal.strip()
        self._bridge = AgentBridge(
            config_path=self._config,
            workspace=self._workspace,
            session_id="cli",
        )
        self._running = False
        self._thought_buf = ""
        self._mode = "agent"

    def compose(self) -> ComposeResult:
        yield MangoHeader(id="header")
        with Vertical(id="main"):
            yield TranscriptLog(id="transcript")
            with Horizontal(id="composer-row"):
                yield Static("❯", id="prompt-glyph")
                yield ComposerInput(id="composer")
        yield MangoStatusBar(id="status")

    def on_mount(self) -> None:
        header = self.query_one(MangoHeader)
        header.set_workspace(self._workspace)
        header.set_mode(self._mode)
        status = self.query_one(MangoStatusBar)
        status.set_ready()
        status.set_mode(self._mode)
        transcript = self.query_one(TranscriptLog)
        transcript.push_banner(str(self._workspace))
        transcript.push_system(f"config {short_path(self._config)}")
        self._refresh_prompt_glyph()
        composer = self.query_one(ComposerInput)
        composer.focus()
        if self._initial_goal:
            composer.load_text(self._initial_goal)
            self.call_after_refresh(self.action_submit_goal)

    def action_clear_transcript(self) -> None:
        log = self.query_one(TranscriptLog)
        log.clear()
        log.push_banner(str(self._workspace), self._bridge.model_path)
        log.push_system("transcript cleared")

    def action_cancel_run(self) -> None:
        if not self._running:
            return
        self._bridge.cancel()
        self.query_one(TranscriptLog).push_system("cancelling…")

    def action_cancel_or_quit(self) -> None:
        if self._running:
            self.action_cancel_run()
            return
        self.exit()

    def on_composer_input_submitted(self, _event: ComposerInput.Submitted) -> None:
        self.action_submit_goal()

    def action_submit_goal(self) -> None:
        if self._running:
            return
        composer = self.query_one(ComposerInput)
        raw = composer.text.strip()
        if not raw:
            self.query_one(MangoStatusBar).set_ready("empty")
            return

        parsed = parse_slash(raw)
        if parsed.kind == "local" and parsed.command is not None:
            composer.load_text("")
            self._handle_local(parsed.command.name)
            return

        if parsed.kind == "plain" and not parsed.goal:
            self.query_one(TranscriptLog).push_system("that command needs an argument — try /help")
            return

        mode = parsed.mode if parsed.kind == "mode" else ""
        goal = parsed.goal
        display = parsed.display or goal
        self._mode = mode or "agent"
        self._refresh_prompt_glyph()
        self.query_one(MangoHeader).set_mode(self._mode)
        self.query_one(MangoStatusBar).set_mode(self._mode)

        composer.disabled = True
        self._running = True
        self._thought_buf = ""
        self.query_one(TranscriptLog).push_user(display, mode=self._mode if mode else "")
        self.query_one(MangoStatusBar).set_running("loading model", mode=self._mode)
        composer.load_text("")
        self._run_goal_worker(goal, mode)

    def _handle_local(self, name: str) -> None:
        log = self.query_one(TranscriptLog)
        if name == "help":
            log.push_markup(help_text())
            return
        if name == "clear":
            self.action_clear_transcript()
            return
        if name == "status":
            model = self._bridge.model_path or "(not loaded yet)"
            color = SLASH_COLORS.get(self._mode, "#e8943a")
            log.push_markup(
                "[#e8943a]status[/]\n"
                f"  [#7a7268]workspace[/]  [#a89f94]{short_path(self._workspace, 64)}[/]\n"
                f"  [#7a7268]config[/]     [#a89f94]{short_path(self._config, 64)}[/]\n"
                f"  [#7a7268]mode[/]       [{color}]{self._mode}[/]\n"
                f"  [#7a7268]model[/]      [#a89f94]{model}[/]"
            )
            return
        if name == "quit":
            self.exit()

    def _refresh_prompt_glyph(self) -> None:
        glyph = self.query_one("#prompt-glyph", Static)
        color = SLASH_COLORS.get(self._mode, "#e8943a")
        glyph.update(f"[{color}]❯[/]")

    @work(thread=True, exclusive=True)
    def _run_goal_worker(self, goal: str, mode: str) -> None:
        try:
            self._bridge.attach_event_handler(self._on_agent_event)
            self.call_from_thread(self._status_running, "thinking", mode)
            self._bridge.load()
            model = self._bridge.model_path
            if model:
                self.call_from_thread(self._set_model_header, model)
            result = self._bridge.run(goal, mode=mode)
            self.call_from_thread(self._on_run_finished, result)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self._on_run_error, str(exc))

    def _set_model_header(self, model: str) -> None:
        self.query_one(MangoHeader).set_model(model)

    def _status_running(self, detail: str, mode: str = "") -> None:
        self.query_one(MangoStatusBar).set_running(detail, mode=mode or self._mode)

    def _on_agent_event(self, message: dict[str, Any]) -> None:
        event = str(message.get("event") or "")
        payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
        self.call_from_thread(self._handle_event, event, payload)

    def _handle_event(self, event: str, payload: dict[str, Any]) -> None:
        transcript = self.query_one(TranscriptLog)
        status = self.query_one(MangoStatusBar)

        if event == "agent.token":
            delta = str(payload.get("delta") or "")
            if payload.get("done"):
                text = str(payload.get("text") or self._thought_buf)
                if text.strip():
                    transcript.push_thought(text)
                self._thought_buf = ""
                return
            if delta:
                self._thought_buf += delta
            return

        if event == "agent.tool":
            title = str(payload.get("title") or payload.get("name") or "tool")
            blocked = bool(payload.get("blocked"))
            ok = payload.get("ok", True)
            transcript.push_tool(title, ok=bool(ok), blocked=blocked)
            status.set_running(title[:48], mode=self._mode)
            return

        if event == "agent.file":
            path = str(payload.get("path") or "")
            action = str(payload.get("action") or "edited")
            added = int(payload.get("added") or 0)
            removed = int(payload.get("removed") or 0)
            transcript.push_file(path, action=action, added=added, removed=removed)
            return

        if event == "agent.verification":
            transcript.push_verify(bool(payload.get("ok")), str(payload.get("report") or ""))
            return

        if event == "agent.syntax":
            path = str(payload.get("path") or "")
            message = str(payload.get("message") or "syntax error")
            transcript.push_error(f"{path}: {message}")
            return

        if event == "agent.final":
            transcript.push_final(str(payload.get("text") or ""))
            return

        if event == "agent.error":
            transcript.push_error(str(payload.get("text") or "unknown error"))
            return

        if event == "agent.started":
            ws = str(payload.get("workspace") or self._workspace)
            status.set_running(short_path(ws, 40), mode=self._mode)

    def _on_run_finished(self, result: Any) -> None:
        self._running = False
        composer = self.query_one(ComposerInput)
        composer.disabled = False
        composer.focus()
        status = self.query_one(MangoStatusBar)
        reason = getattr(getattr(result, "stop_reason", None), "value", "done")
        iterations = getattr(result, "iterations", 0)
        if getattr(result, "error", None):
            self.query_one(TranscriptLog).push_error(str(result.error))
            status.set_error(f"{reason} · {iterations} iters")
        else:
            status.set_ready(f"{reason} · {iterations} iters")

    def _on_run_error(self, message: str) -> None:
        self._running = False
        composer = self.query_one(ComposerInput)
        composer.disabled = False
        composer.focus()
        self.query_one(TranscriptLog).push_error(message)
        self.query_one(MangoStatusBar).set_error(message[:80])

    def on_unmount(self) -> None:
        self._bridge.unload()
