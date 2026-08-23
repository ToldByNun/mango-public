"""CLI slash commands — Aider / Claude Code style."""

from __future__ import annotations

from dataclasses import dataclass

# Keep hues aligned with apps/electron/.../slashCommands.ts
SLASH_COLORS: dict[str, str] = {
    "plan": "#5b9fd4",
    "ask": "#4ec99a",
    "debug": "#e8786e",
    "refactor": "#b794f6",
    "clear": "#9a9288",
    "help": "#e8943a",
    "quit": "#9a9288",
    "status": "#a89f94",
    "agent": "#e8943a",
}


@dataclass(frozen=True)
class SlashCommand:
    name: str
    trigger: str
    description: str
    takes_arg: bool
    color: str
    local: bool = False
    mode: str = ""


COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand("help", "/help", "Show commands and keybindings", False, SLASH_COLORS["help"], local=True),
    SlashCommand("clear", "/clear", "Clear the transcript", False, SLASH_COLORS["clear"], local=True),
    SlashCommand("status", "/status", "Show workspace, model, and mode", False, SLASH_COLORS["status"], local=True),
    SlashCommand("quit", "/quit", "Exit Mango", False, SLASH_COLORS["quit"], local=True),
    SlashCommand("ask", "/ask", "Read-only Q&A over the workspace", True, SLASH_COLORS["ask"], mode="ask"),
    SlashCommand("plan", "/plan", "Draft a plan without editing files", True, SLASH_COLORS["plan"], mode="plan"),
    SlashCommand("debug", "/debug", "Debug a failure or bug", True, SLASH_COLORS["debug"], mode="debug"),
    SlashCommand(
        "refactor",
        "/refactor",
        "Focused rename / cleanup",
        True,
        SLASH_COLORS["refactor"],
        mode="refactor",
    ),
)


@dataclass(frozen=True)
class ParsedSlash:
    kind: str  # local | mode | plain
    command: SlashCommand | None = None
    mode: str = ""
    goal: str = ""
    display: str = ""


def parse_slash(text: str) -> ParsedSlash:
    raw = text.strip()
    if not raw:
        return ParsedSlash(kind="plain", goal="")
    ranked = sorted(COMMANDS, key=lambda c: len(c.trigger), reverse=True)
    lower = raw.lower()
    for cmd in ranked:
        trig = cmd.trigger.lower()
        if lower == trig or lower.startswith(trig + " "):
            rest = raw[len(cmd.trigger) :].strip()
            if cmd.local:
                return ParsedSlash(kind="local", command=cmd, goal=rest, display=cmd.trigger)
            if cmd.takes_arg and not rest:
                return ParsedSlash(kind="plain", goal="")
            return ParsedSlash(
                kind="mode",
                command=cmd,
                mode=cmd.mode,
                goal=rest,
                display=f"{cmd.trigger} {rest}".strip(),
            )
    return ParsedSlash(kind="plain", goal=raw, display=raw)


def help_text() -> str:
    lines = ["[#e8943a]Commands[/]", ""]
    for cmd in COMMANDS:
        arg = " [arg]" if cmd.takes_arg else ""
        lines.append(f"  [{cmd.color}]{cmd.trigger}{arg}[/]  [#7a7268]{cmd.description}[/]")
    lines.extend(
        [
            "",
            "[#e8943a]Keys[/]",
            "  [#a89f94]⏎[/]        send",
            "  [#a89f94]⇧⏎[/]       newline",
            "  [#a89f94]esc[/]      cancel run",
            "  [#a89f94]^l[/]       clear transcript",
            "  [#a89f94]^c[/]       cancel / quit",
            "",
            "[#7a7268]Tip: /ask to inspect, /plan before big edits.[/]",
        ]
    )
    return "\n".join(lines)
