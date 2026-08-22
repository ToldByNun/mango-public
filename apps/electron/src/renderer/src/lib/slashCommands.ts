/** Slash commands available in the composer (Discord-style). */

export type SlashCommand = {
  id: string;
  name: string;
  /** Shown as `/plan` */
  trigger: string;
  description: string;
  /** Parameter label in the tiny tooltip (empty if none) */
  paramLabel: string;
  paramHint: string;
  source: string;
  /** Needs text after the trigger before submit */
  takesArg: boolean;
  /** Handled in the UI only — no agent run */
  localOnly?: boolean;
};

export const SLASH_COMMANDS: SlashCommand[] = [
  {
    id: "plan",
    name: "plan",
    trigger: "/plan",
    description: "Draft a markdown plan (flow, details, todos) without changing files.",
    paramLabel: "goal",
    paramHint: "What should we plan?",
    source: "Mango",
    takesArg: true,
  },
  {
    id: "ask",
    name: "ask",
    trigger: "/ask",
    description: "Ask a question — search the codebase and get a long, detailed answer.",
    paramLabel: "message",
    paramHint: "Your question",
    source: "Mango",
    takesArg: true,
  },
  {
    id: "debug",
    name: "debug",
    trigger: "/debug",
    description: "Debug a specific issue you describe.",
    paramLabel: "message",
    paramHint: "What to debug",
    source: "Mango",
    takesArg: true,
  },
  {
    id: "refactor",
    name: "refactor",
    trigger: "/refactor",
    description: "Isolated rename/cleanup via edit_symbol or rename_symbol — no unrelated file scans.",
    paramLabel: "symbol",
    paramHint: "Symbol to refactor",
    source: "Mango",
    takesArg: true,
  },
  {
    id: "clear",
    name: "clear",
    trigger: "/clear",
    description: "Clear conversation context in this session.",
    paramLabel: "",
    paramHint: "",
    source: "Mango",
    takesArg: false,
    localOnly: true,
  },
];

/** Match while the user is still typing a slash command (before a space commits it). */
export function matchSlashQuery(text: string): string | null {
  const m = /^(\/[^\s]*)$/.exec(text);
  return m ? m[1].toLowerCase() : null;
}

export function filterSlashCommands(query: string): SlashCommand[] {
  const q = query.toLowerCase();
  return SLASH_COMMANDS.filter(
    (cmd) => cmd.trigger.startsWith(q) || cmd.name.startsWith(q.replace(/^\//, "")),
  );
}

/** Active command once committed (`/plan …` or bare `/clear`). */
export function activeSlashCommand(text: string): SlashCommand | null {
  const trimmed = text.trimStart();
  const ranked = [...SLASH_COMMANDS].sort((a, b) => b.trigger.length - a.trigger.length);
  for (const cmd of ranked) {
    if (cmd.takesArg) {
      if (trimmed.startsWith(`${cmd.trigger} `)) return cmd;
    } else if (trimmed === cmd.trigger || trimmed.startsWith(`${cmd.trigger} `)) {
      return cmd;
    }
  }
  return null;
}

/** Orange prefix + remainder for the input highlight overlay. */
export function slashInputHighlight(text: string): { prefix: string; rest: string } | null {
  const lead = text.match(/^\s*/)?.[0] ?? "";
  const body = text.slice(lead.length);
  const ranked = [...SLASH_COMMANDS].sort((a, b) => b.trigger.length - a.trigger.length);
  for (const cmd of ranked) {
    if (
      body === cmd.trigger ||
      body.startsWith(`${cmd.trigger} `) ||
      body.startsWith(`${cmd.trigger}\n`)
    ) {
      return { prefix: lead + cmd.trigger, rest: body.slice(cmd.trigger.length) };
    }
  }
  return null;
}

export type ParsedSlash =
  | { kind: "clear" }
  | { kind: "mode"; mode: "plan" | "ask" | "debug" | "refactor"; cleanGoal: string; display: string }
  | { kind: "plain"; cleanGoal: string };

/** Parse composer submit text into a mode or local action. */
export function parseSlashGoal(goal: string): ParsedSlash {
  const trimmed = goal.trim();
  const ranked = [...SLASH_COMMANDS].sort((a, b) => b.trigger.length - a.trigger.length);
  for (const cmd of ranked) {
    const re = new RegExp(`^${escapeReg(cmd.trigger)}(?:\\s+|$)`, "i");
    const m = re.exec(trimmed);
    if (!m) continue;
    if (cmd.localOnly && cmd.id === "clear") return { kind: "clear" };
    const cleanGoal = trimmed.slice(m[0].length).trim();
    if (cmd.takesArg && !cleanGoal) {
      return { kind: "plain", cleanGoal: "" };
    }
    if (cmd.id === "plan" || cmd.id === "ask" || cmd.id === "debug" || cmd.id === "refactor") {
      return {
        kind: "mode",
        mode: cmd.id,
        cleanGoal,
        display: `${cmd.trigger} ${cleanGoal}`.trim(),
      };
    }
  }
  return { kind: "plain", cleanGoal: trimmed };
}

function escapeReg(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
