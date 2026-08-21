from __future__ import annotations

from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from mango_cli.agent_bridge import AgentBridge
from mango_cli.paths import default_workspace, resolve_cli_config
from mango_cli.widgets import ComposerInput, MangoHeader, MangoStatusBar, TranscriptLog


class MangoApp(App):
    """Console-first Mango TUI — same agent loop as the Electron app."""

    CSS_PATH = "theme.tcss"
    TITLE = "mango"
    # No Footer / command palette chrome — keyboard only.
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
        self._model_name = "local model"

    def compose(self) -> ComposeResult:
        yield MangoHeader(id="header")
        with Vertical(id="main"):
            yield TranscriptLog(id="transcript")
            with Horizontal(id="composer-row"):
                yield Static(">", id="prompt-glyph")
                yield ComposerInput(id="composer", soft_wrap=True, show_line_numbers=False)
        yield MangoStatusBar(id="status")

    def on_mount(self) -> None:
        self.query_one(MangoHeader).set_workspace(self._workspace)
        status = self.query_one(MangoStatusBar)
        status.set_ready()
        transcript = self.query_one(TranscriptLog)
        transcript.push_system(f"config {_short(self._config)}")
        transcript.push_system("type a goal · ^⏎ / ^j run · esc cancel · ^c quit")
        composer = self.query_one(ComposerInput)
        composer.focus()
        if self._initial_goal:
            composer.load_text(self._initial_goal)
            self.call_after_refresh(self.action_submit_goal)

    def action_clear_transcript(self) -> None:
        self.query_one(TranscriptLog).clear()

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

    def action_submit_goal(self) -> None:
        if self._running:
            return
        composer = self.query_one(ComposerInput)
        goal = composer.text.strip()
        if not goal:
            self.query_one(MangoStatusBar).set_ready("empty goal")
            return
        composer.disabled = True
        self._running = True
        self._thought_buf = ""
        self.query_one(TranscriptLog).push_user(goal)
        self.query_one(MangoStatusBar).set_running("loading model")
        composer.clear()
        self._run_goal_worker(goal)

    @work(thread=True, exclusive=True)
    def _run_goal_worker(self, goal: str) -> None:
        try:
            self._bridge.attach_event_handler(self._on_agent_event)
            self.call_from_thread(self._status_running, "thinking")
            self._bridge.load()
            result = self._bridge.run(goal)
            self.call_from_thread(self._on_run_finished, result)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self._on_run_error, str(exc))

    def _status_running(self, detail: str) -> None:
        self.query_one(MangoStatusBar).set_running(detail)

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
            status.set_running(title[:48])
            return

        if event == "agent.file":
            path = str(payload.get("path") or "")
            action = str(payload.get("action") or "edited")
            added = int(payload.get("added") or 0)
            removed = int(payload.get("removed") or 0)
            transcript.push_file(path, action=action, added=added, removed=removed)
            return

        if event == "agent.verification":
            ok = bool(payload.get("ok"))
            report = str(payload.get("report") or "")
            transcript.push_verify(ok, report)
            return

        if event == "agent.syntax":
            path = str(payload.get("path") or "")
            message = str(payload.get("message") or "syntax error")
            transcript.push_error(f"{path}: {message}")
            return

        if event == "agent.final":
            text = str(payload.get("text") or "")
            transcript.push_final(text)
            return

        if event == "agent.error":
            transcript.push_error(str(payload.get("text") or "unknown error"))
            return

        if event == "agent.started":
            ws = str(payload.get("workspace") or self._workspace)
            status.set_running(_short(ws, 40))

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


def _short(path: Path | str, max_len: int = 56) -> str:
    text = str(path).replace("\\", "/")
    if len(text) <= max_len:
        return text
    return "…" + text[-(max_len - 1) :]
