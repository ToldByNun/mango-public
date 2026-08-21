import type { AgentEvent, Session, TranscriptBlock } from "@shared/events";
import { stripThoughtMarkup } from "./thoughtSanitize";

export function newId(): string {
  return crypto.randomUUID();
}

export function composeAgentGoal(
  priorUserMessages: string[],
  latest: string,
  lastSummary = "",
): string {
  const prior = priorUserMessages.map((item) => item.trim()).filter(Boolean);
  const follow = latest.trim();
  if (prior.length === 0) return follow;
  const original = prior[0].length > 1600 ? `${prior[0].slice(0, 1597)}...` : prior[0];
  const delivered = lastSummary.trim();
  const clipped =
    delivered.length > 1800 ? `${delivered.slice(0, 1797)}...` : delivered;
  const parts = [
    "You already changed files in this workspace for an earlier request.",
    "Original request:",
    original,
  ];
  if (clipped) {
    parts.push("", "What you already delivered:", clipped);
  }
  parts.push(
    "",
    "Follow-up request:",
    follow,
    "",
    "Read the current implementation and existing tests first.",
    "ask_epistemic must look up concrete symbols (package + symbol), not a whole module.",
    "Then edit. Then run_tests. Do not finish until tests pass.",
    "When tests pass, write a real finish summary: what changed, why, test result.",
  );
  return parts.join("\n");
}

export function titleFromGoal(goal: string): string {
  const line = goal.replace(/\s+/g, " ").trim();
  if (line.length <= 42) return line || "New agent";
  return `${line.slice(0, 41)}…`;
}

export function relativeTime(ts: number, now = Date.now()): string {
  const delta = Math.max(0, now - ts);
  const minutes = Math.floor(delta / 60_000);
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

export function shortPath(path: string): string {
  const normalized = path.replace(/\\/g, "/").replace(/^\.\/+/, "");
  const stripped = normalized
    .replace(/^(home\/user\/|home\/|user\/|workspace\/|project\/|repo\/)+/i, "")
    .replace(/^\/+/, "");
  const parts = stripped.split("/").filter(Boolean);
  if (parts.length === 0) return normalized.split("/").filter(Boolean).at(-1) ?? path;
  if (parts.length <= 2) return parts.join("/");
  return parts.slice(-2).join("/");
}

export function shortWorkspace(path: string): string {
  if (!path) return "No workspace";
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  return parts.at(-1) ?? path;
}

function block(partial: Omit<TranscriptBlock, "id" | "createdAt"> & { id?: string }): TranscriptBlock {
  return {
    id: partial.id ?? newId(),
    createdAt: Date.now(),
    ...partial,
  } as TranscriptBlock;
}

function lastUserIndex(messages: TranscriptBlock[]): number {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].kind === "user") return i;
  }
  return 0;
}

function upsertStream(
  messages: TranscriptBlock[],
  payload: Record<string, unknown>,
  kind: "thought" | "final",
): TranscriptBlock[] {
  const id = String(payload.id ?? "");
  const rawDelta = String(payload.delta ?? "");
  const done = Boolean(payload.done);
  const rawFull = payload.text != null ? String(payload.text) : null;
  const delta = kind === "thought" && /<tool_call\b/i.test(rawDelta) ? "" : rawDelta;
  const full = kind === "thought" && rawFull != null ? stripThoughtMarkup(rawFull) : rawFull;
  const durationMs = Number(payload.duration_ms ?? 0);
  const turnStart = lastUserIndex(messages);
  const idx = id ? messages.findIndex((item, i) => i >= turnStart && item.id === id) : -1;
  if (idx >= 0) {
    const current = messages[idx];
    if (kind === "thought" && current.kind === "thought") {
      const next = [...messages];
      const combined = full ?? `${current.text}${delta}`;
      const text = stripThoughtMarkup(combined);
      if (!text.trim()) {
        next.splice(idx, 1);
        return next;
      }
      next[idx] = {
        ...current,
        text,
        durationMs: payload.duration_ms != null ? durationMs : current.durationMs,
        streaming: !done,
      };
      return next;
    }
    if (kind === "final" && current.kind === "final") {
      const next = [...messages];
      next[idx] = { ...current, text: full ?? current.text + delta, streaming: !done };
      return next;
    }
  }
  if (kind === "thought") {
    const candidate = stripThoughtMarkup(full ?? delta);
    if (!candidate.trim()) {
      return messages;
    }
  }
  const created =
    kind === "thought"
      ? block({
          id,
          kind: "thought",
          durationMs,
          text: stripThoughtMarkup(full ?? delta),
          streaming: !done,
        })
      : block({
          id,
          kind: "final",
          text: full ?? delta,
          streaming: !done,
        });
  return [...messages, created];
}

function upsertStatus(messages: TranscriptBlock[], payload: Record<string, unknown>): TranscriptBlock[] {
  const id = String(payload.id ?? "");
  const delta = String(payload.delta ?? "");
  const done = Boolean(payload.done);
  const full = payload.text != null ? String(payload.text) : null;
  const idx = id ? messages.findIndex((item) => item.id === id) : -1;
  if (idx >= 0) {
    const current = messages[idx];
    if (current.kind === "status") {
      const next = [...messages];
      const text = full ?? (delta ? current.text + delta : current.text);
      if (done && !text) {
        next.splice(idx, 1);
        return next;
      }
      next[idx] = { ...current, text, streaming: !done };
      return next;
    }
  }
  const text = full ?? delta;
  if (done && !text) return messages;
  return [
    ...messages,
    block({
      id,
      kind: "status",
      text,
      streaming: !done,
    }),
  ];
}

function upsertTool(messages: TranscriptBlock[], payload: Record<string, unknown>): TranscriptBlock[] {
  const id = String(payload.id ?? "");
  const turnStart = lastUserIndex(messages);
  const idx = id ? messages.findIndex((item, i) => i >= turnStart && item.id === id) : -1;
  const title = String(payload.title ?? payload.name ?? "Tool");
  const body = payload.body != null ? String(payload.body) : undefined;
  const streaming = Boolean(payload.streaming);
  const ok = payload.ok != null ? Boolean(payload.ok) : undefined;
  const blocked = Boolean(payload.blocked);
  const patch = {
    kind: "tool" as const,
    title,
    name: payload.name != null ? String(payload.name) : undefined,
    body,
    console: Boolean(payload.console),
    ok,
    blocked,
    streaming,
  };
  if (idx >= 0 && messages[idx].kind === "tool") {
    const next = [...messages];
    next[idx] = { ...messages[idx], ...patch, id };
    return next;
  }
  return [...messages, block({ id, ...patch })];
}

export function applyAgentEvent(session: Session, event: AgentEvent): Session {
  const payload = event.payload ?? {};
  const next: Session = { ...session, messages: [...session.messages], updatedAt: Date.now() };

  switch (event.event) {
    case "agent.started":
      next.status = "running";
      next.messages = next.messages.map((item) =>
        "streaming" in item && item.streaming ? { ...item, streaming: false } : item,
      );
      if (typeof payload.workspace === "string" && payload.workspace) {
        next.workspace = payload.workspace;
      }
      break;
    case "agent.title": {
      const title = String(payload.title ?? "").trim();
      if (title) next.title = title;
      break;
    }
    case "agent.token": {
      const channel = String(payload.channel ?? "thought");
      if (channel === "status") {
        next.messages = upsertStatus(next.messages, payload);
        break;
      }
      next.messages = upsertStream(
        next.messages,
        payload,
        channel === "assistant" || channel === "final" ? "final" : "thought",
      );
      break;
    }
    case "agent.thought": {
      // Fold discrete thought events into the single turn thought stream.
      const text = stripThoughtMarkup(String(payload.text ?? ""));
      if (!text.trim()) break;
      const turnStart = lastUserIndex(next.messages);
      const existing = next.messages.findIndex(
        (item, i) => i >= turnStart && item.kind === "thought",
      );
      if (existing >= 0) {
        const current = next.messages[existing];
        if (current.kind === "thought") {
          const merged = current.text.trim()
            ? `${current.text.trim()}\n\n${text.trim()}`
            : text.trim();
          next.messages[existing] = {
            ...current,
            text: merged,
            durationMs: current.durationMs + Number(payload.duration_ms ?? 0),
            streaming: false,
          };
          break;
        }
      }
      next.messages.push(
        block({
          kind: "thought",
          durationMs: Number(payload.duration_ms ?? 0),
          text,
        }),
      );
      break;
    }
    case "agent.file": {
      const action = payload.action === "read" ? "read" : payload.action === "created" ? "created" : "edited";
      next.messages.push(
        block({
          kind: "file",
          action,
          path: String(payload.path ?? ""),
          absolutePath:
            payload.absolute_path != null ? String(payload.absolute_path) : undefined,
          added: payload.added != null ? Number(payload.added) : undefined,
          removed: payload.removed != null ? Number(payload.removed) : undefined,
          startLine: payload.start_line != null ? Number(payload.start_line) : undefined,
          endLine: payload.end_line != null ? Number(payload.end_line) : undefined,
          diff: payload.diff != null ? String(payload.diff) : undefined,
        }),
      );
      break;
    }
    case "agent.tool": {
      const id = payload.id != null ? String(payload.id) : "";
      const blocked = Boolean(payload.blocked);
      if (id) {
        next.messages = upsertTool(next.messages, payload);
      } else {
        next.messages.push(
          block({
            kind: "tool",
            title: String(payload.title ?? payload.name ?? "Tool"),
            name: payload.name != null ? String(payload.name) : undefined,
            body: payload.body != null ? String(payload.body) : undefined,
            console: Boolean(payload.console),
            ok: payload.ok != null ? Boolean(payload.ok) : undefined,
            blocked,
            streaming: Boolean(payload.streaming),
          }),
        );
      }
      break;
    }
    case "agent.verification":
      next.messages.push(
        block({
          kind: "verification",
          ok: Boolean(payload.ok),
          report: String(payload.report ?? ""),
        }),
      );
      break;
    case "agent.syntax":
      next.messages.push(
        block({
          kind: "syntax",
          path: String(payload.path ?? ""),
          message: String(payload.message ?? ""),
        }),
      );
      break;
    case "agent.experiment":
      next.messages.push(
        block({
          kind: "experiment",
          hypothesis: String(payload.hypothesis ?? ""),
          before: payload.before != null ? Number(payload.before) : undefined,
          after: payload.after != null ? Number(payload.after) : undefined,
          unit: String(payload.unit ?? "ms"),
          decision: payload.decision === "revert" ? "revert" : "keep",
          deltaPct: payload.delta_pct != null ? Number(payload.delta_pct) : undefined,
          reason: String(payload.reason ?? ""),
        }),
      );
      break;
    case "agent.final": {
      const text = String(payload.text ?? "");
      const turnStart = lastUserIndex(next.messages);
      const streaming = next.messages.findIndex(
        (item, i) => i >= turnStart && item.kind === "final" && item.streaming,
      );
      if (streaming >= 0) {
        const current = next.messages[streaming];
        if (current.kind === "final") {
          next.messages[streaming] = { ...current, text: text || current.text, streaming: false };
          break;
        }
      }
      next.messages.push(block({ kind: "final", text }));
      break;
    }
    case "agent.error":
      next.status = "error";
      next.messages.push(block({ kind: "error", text: String(payload.text ?? "error") }));
      break;
    case "agent.stopped": {
      const reason = String(payload.reason ?? "stopped");
      const errText = String(payload.error ?? "").trim();
      next.messages = next.messages.map((item) =>
        "streaming" in item && item.streaming ? { ...item, streaming: false } : item,
      );
      if (reason === "completed") {
        next.status = "idle";
      } else if (reason === "cancelled") {
        next.status = "idle";
      } else if (reason === "error") {
        next.status = "error";
        if (errText && !next.messages.some((m) => m.kind === "error" && "text" in m && m.text === errText)) {
          next.messages.push(block({ kind: "error", text: errText }));
        }
      } else {
        next.status = "stopped";
        const note = errText || reason.replace(/_/g, " ");
        if (note) {
          next.messages.push(block({ kind: "status", text: note }));
        }
      }
      if (next.title === "New agent" || !next.title.trim()) {
        const firstUser = next.messages.find((m) => m.kind === "user");
        if (firstUser && "text" in firstUser && firstUser.text) {
          const line = firstUser.text.split("\n")[0].trim();
          next.title = line.length <= 48 ? line : `${line.slice(0, 47)}…`;
        }
      }
      break;
    }
    default:
      break;
  }
  return next;
}

export function actionSummary(messages: TranscriptBlock[]): {
  edited: number;
  read: number;
  verify?: "pass" | "fail";
} {
  let edited = 0;
  let read = 0;
  let verify: "pass" | "fail" | undefined;
  for (const item of messages) {
    if (item.kind === "file" && item.action === "read") read += 1;
    if (item.kind === "file" && item.action !== "read") edited += 1;
    if (item.kind === "verification") verify = item.ok ? "pass" : "fail";
  }
  return { edited, read, verify };
}

export function createSession(workspace: string, title = "New agent"): Session {
  const now = Date.now();
  return {
    id: newId(),
    title,
    workspace,
    createdAt: now,
    updatedAt: now,
    messages: [],
    status: "idle",
  };
}

