import type { TranscriptBlock } from "@shared/events";
import { shortPath } from "./session";
import { isEmptyThought } from "./thoughtSanitize";

export type ThoughtBlock = Extract<TranscriptBlock, { kind: "thought" }>;
export type FileBlock = Extract<TranscriptBlock, { kind: "file" }>;
export type ToolBlock = Extract<TranscriptBlock, { kind: "tool" }>;

export type ActivitySegment =
  | { id: string; kind: "thoughts"; items: ThoughtBlock[]; durationMs: number; streaming: boolean }
  | { id: string; kind: "file"; item: FileBlock }
  | { id: string; kind: "tool"; item: ToolBlock }
  | { id: string; kind: "verification"; item: Extract<TranscriptBlock, { kind: "verification" }> }
  | { id: string; kind: "syntax"; item: Extract<TranscriptBlock, { kind: "syntax" }> }
  | { id: string; kind: "experiment"; item: Extract<TranscriptBlock, { kind: "experiment" }> }
  | { id: string; kind: "status"; item: Extract<TranscriptBlock, { kind: "status" }> };

const SEARCH_TOOLS = new Set(["search_code", "web_research"]);
const COMMAND_TOOLS = new Set(["run_terminal_command", "run_tests", "measure"]);
const EXPLORE_TOOLS = new Set([
  "read_file",
  "codebase_lookup",
  "ask_epistemic",
  "package_source_lookup",
  "doc_lookup",
]);

function toolName(item: ToolBlock): string {
  return (item.name || "").toLowerCase();
}

export function pathLeaf(path: string): string {
  const leaf = shortPath(path);
  return leaf.includes("/") || leaf.includes("\\") ? leaf.split(/[/\\]/).pop() || leaf : leaf;
}

/** Split turn into user / activity / finale blocks. */
export function splitTurn(turn: TranscriptBlock[]): {
  user: TranscriptBlock | null;
  activity: TranscriptBlock[];
  finale: TranscriptBlock[];
} {
  let user: TranscriptBlock | null = null;
  const activity: TranscriptBlock[] = [];
  const finale: TranscriptBlock[] = [];
  for (const item of turn) {
    if (item.kind === "user" && !user) {
      user = item;
      continue;
    }
    if (item.kind === "final" || item.kind === "error") {
      finale.push(item);
      continue;
    }
    if (item.kind === "user") continue;
    // Skip duplicate read_file tool chips when a file event exists later — keep tools for live status.
    activity.push(item);
  }
  return { user, activity, finale };
}

/** Consecutive thoughts merge; tools/files stay in chronological order between them. */
export function segmentActivity(blocks: TranscriptBlock[]): ActivitySegment[] {
  const segments: ActivitySegment[] = [];
  let thoughtBuf: ThoughtBlock[] = [];

  const flushThoughts = (): void => {
    const items = thoughtBuf.filter((t) => t.streaming || !isEmptyThought(t.text || ""));
    thoughtBuf = [];
    if (items.length === 0) return;
    const durationMs = items.reduce((sum, t) => sum + (t.durationMs || 0), 0);
    const streaming = items.some((t) => Boolean(t.streaming));
    segments.push({
      id: `thoughts-${items[0].id}`,
      kind: "thoughts",
      items,
      durationMs,
      streaming,
    });
  };

  for (const item of blocks) {
    if (item.kind === "thought") {
      thoughtBuf.push(item);
      continue;
    }
    flushThoughts();
    if (item.kind === "file") {
      segments.push({ id: item.id, kind: "file", item });
    } else if (item.kind === "tool") {
      if (toolName(item) === "read_file" && !item.streaming) continue;
      segments.push({ id: item.id, kind: "tool", item });
    } else if (item.kind === "verification") {
      segments.push({ id: item.id, kind: "verification", item });
    } else if (item.kind === "syntax") {
      segments.push({ id: item.id, kind: "syntax", item });
    } else if (item.kind === "experiment") {
      segments.push({ id: item.id, kind: "experiment", item });
    } else if (item.kind === "status" && item.text) {
      segments.push({ id: item.id, kind: "status", item });
    }
  }
  flushThoughts();
  return segments;
}

export type TurnActivityStats = {
  edited: number;
  created: number;
  explored: number;
  searches: number;
  commands: number;
  added: number;
  removed: number;
};

export function collectTurnStats(turn: TranscriptBlock[]): TurnActivityStats {
  let edited = 0;
  let created = 0;
  let explored = 0;
  let searches = 0;
  let commands = 0;
  let added = 0;
  let removed = 0;
  const seenSearch = new Set<string>();
  const seenExplore = new Set<string>();

  for (const item of turn) {
    if (item.kind === "file") {
      if (item.action === "read") {
        const key = item.path || item.id;
        if (!seenExplore.has(key)) {
          seenExplore.add(key);
          explored += 1;
        }
      } else if (item.action === "created") {
        created += 1;
        added += item.added ?? 0;
        removed += item.removed ?? 0;
      } else {
        edited += 1;
        added += item.added ?? 0;
        removed += item.removed ?? 0;
      }
      continue;
    }
    if (item.kind !== "tool") continue;
    const name = toolName(item);
    if (name === "read_file") continue;
    if (SEARCH_TOOLS.has(name) || /search/i.test(item.title)) {
      const key = item.id || `${name}:${item.title}`;
      if (!seenSearch.has(key)) {
        seenSearch.add(key);
        searches += 1;
      }
    } else if (COMMAND_TOOLS.has(name) || /^ran\b/i.test(item.title)) {
      commands += 1;
    } else if (EXPLORE_TOOLS.has(name)) {
      const key = item.id || item.title;
      if (!seenExplore.has(key)) {
        seenExplore.add(key);
        explored += 1;
      }
    }
  }

  return { edited, created, explored, searches, commands, added, removed };
}

export function formatTurnSummary(stats: TurnActivityStats): string | null {
  const parts: string[] = [];
  const changed = stats.edited + stats.created;
  if (changed > 0) parts.push(`Edited ${changed} file${changed === 1 ? "" : "s"}`);
  if (stats.explored > 0) parts.push(`explored ${stats.explored} file${stats.explored === 1 ? "" : "s"}`);
  if (stats.searches > 0) parts.push(`${stats.searches} search${stats.searches === 1 ? "" : "es"}`);
  if (stats.commands > 0) parts.push(`ran ${stats.commands} command${stats.commands === 1 ? "" : "s"}`);
  if (parts.length === 0) return null;
  if (parts.length === 1) return parts[0];
  return `${parts[0]}, ${parts.slice(1).join(", ")}`;
}

export function fileStatusLabel(item: FileBlock): { verb: string; meta: string } {
  const name = pathLeaf(item.path);
  if (item.action === "read") {
    const start = item.startLine;
    const end = item.endLine;
    const range = start != null && end != null ? ` L${start}-${end}` : "";
    return { verb: "Read", meta: `${name}${range}` };
  }
  if (item.action === "created") {
    const diffs = [
      item.added ? `+${item.added}` : "",
      item.removed ? `-${item.removed}` : "",
    ]
      .filter(Boolean)
      .join(" ");
    return { verb: "Created", meta: diffs ? `${name} ${diffs}` : name };
  }
  const diffs = [
    item.added ? `+${item.added}` : "",
    item.removed ? `-${item.removed}` : "",
  ]
    .filter(Boolean)
    .join(" ");
  return { verb: "Edited", meta: diffs ? `${name} ${diffs}` : name };
}

export function toolStatusLabel(item: ToolBlock): string {
  if (item.blocked) return item.title || "Blocked";
  if (item.streaming) return item.title || "Running…";
  const name = toolName(item);
  if (name === "search_code" || /search/i.test(item.title)) {
    return item.title.replace(/^Searching\b/i, "Grepped").replace(/…$/, "");
  }
  return item.title.replace(/…$/, "");
}

export type ExperimentBlock = Extract<TranscriptBlock, { kind: "experiment" }>;

export function formatSignedPct(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${Math.abs(value).toFixed(1)}%`;
}

export function experimentStatusMeta(item: ExperimentBlock): string {
  const delta = item.deltaPct;
  const deltaText = delta != null && Number.isFinite(delta) ? formatSignedPct(delta) : "";
  if (item.decision === "revert" && item.reason === "regression") {
    return deltaText ? `REGRESSION (${deltaText})` : "REGRESSION";
  }
  if (item.reason === "unsupported") {
    return deltaText ? `unsupported ${deltaText}` : "unsupported";
  }
  if (deltaText) return deltaText;
  if (item.reason && item.reason !== "keep") return item.reason.replace(/_/g, " ");
  return item.decision === "keep" ? "" : item.decision;
}

export type DiffLine = {
  type: "ctx" | "add" | "del" | "hunk" | "meta";
  text: string;
  oldNo?: number;
  newNo?: number;
};

export function parseUnifiedDiff(diff: string, limit = 80): DiffLine[] {
  const out: DiffLine[] = [];
  let oldNo = 0;
  let newNo = 0;
  for (const raw of diff.split("\n")) {
    if (out.length >= limit) {
      out.push({ type: "meta", text: "…" });
      break;
    }
    if (raw.startsWith("@@")) {
      const m = raw.match(/@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)/);
      if (m) {
        oldNo = parseInt(m[1], 10);
        newNo = parseInt(m[2], 10);
      }
      out.push({ type: "hunk", text: raw });
      continue;
    }
    if (raw.startsWith("---") || raw.startsWith("+++")) {
      out.push({ type: "meta", text: raw });
      continue;
    }
    if (raw.startsWith("+")) {
      out.push({ type: "add", text: raw.slice(1), newNo });
      newNo += 1;
      continue;
    }
    if (raw.startsWith("-")) {
      out.push({ type: "del", text: raw.slice(1), oldNo });
      oldNo += 1;
      continue;
    }
    if (raw.startsWith(" ")) {
      out.push({ type: "ctx", text: raw.slice(1), oldNo, newNo });
      oldNo += 1;
      newNo += 1;
      continue;
    }
    out.push({ type: "ctx", text: raw, oldNo, newNo });
  }
  return out;
}
