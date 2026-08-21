import type { Session, TranscriptBlock } from "@shared/events";

export type SessionStatusKind = "idle" | "running" | "pass" | "fail" | "error";

export type TimeBucket = "today" | "yesterday" | "thisWeek" | "older";

export type TimeBucketLabel = "Today" | "Yesterday" | "This week" | "Older";

const TIME_BUCKET_ORDER: TimeBucket[] = ["today", "yesterday", "thisWeek", "older"];

const TIME_BUCKET_LABELS: Record<TimeBucket, TimeBucketLabel> = {
  today: "Today",
  yesterday: "Yesterday",
  thisWeek: "This week",
  older: "Older",
};

export function timeBucket(ts: number, now = Date.now()): TimeBucket {
  const date = new Date(ts);
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const weekStart = new Date(today);
  weekStart.setDate(weekStart.getDate() - 6);

  if (date >= today) return "today";
  if (date >= yesterday) return "yesterday";
  if (date >= weekStart) return "thisWeek";
  return "older";
}

export function timeBucketLabel(bucket: TimeBucket): TimeBucketLabel {
  return TIME_BUCKET_LABELS[bucket];
}

export function groupSessionsByTime(sessions: Session[]): Map<TimeBucket, Session[]> {
  const map = new Map<TimeBucket, Session[]>();
  for (const bucket of TIME_BUCKET_ORDER) {
    map.set(bucket, []);
  }
  for (const session of sessions) {
    map.get(timeBucket(session.updatedAt))!.push(session);
  }
  for (const [, list] of map) {
    list.sort((a, b) => b.updatedAt - a.updatedAt);
  }
  return map;
}

export function sessionStatus(session: Session): SessionStatusKind {
  if (session.status === "running") return "running";
  if (session.status === "error") return "error";
  for (let i = session.messages.length - 1; i >= 0; i -= 1) {
    const block = session.messages[i];
    if (block.kind === "verification") return block.ok ? "pass" : "fail";
    if (block.kind === "tool" && block.name === "run_tests" && block.ok != null) {
      return block.ok ? "pass" : "fail";
    }
    if (block.kind === "error") return "error";
  }
  return "idle";
}

export function sessionSubtitle(session: Session, modelName: string): string {
  const file = lastTouchedFile(session.messages);
  const parts = [file, shortModel(modelName)].filter(Boolean);
  return parts.join(" · ");
}

function shortModel(name: string): string {
  return name.replace(/\s+Q\d_K_\w+$/i, "").trim() || name;
}

function lastTouchedFile(messages: TranscriptBlock[]): string | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const block = messages[i];
    if (block.kind === "file" && block.path) {
      const name = block.path.split("/").pop() ?? block.path;
      return name.length > 24 ? `${name.slice(0, 23)}…` : name;
    }
  }
  return null;
}

/** Intent-focused title instead of raw prompt prefix. */
export function sessionDisplayTitle(session: Session): string {
  const raw = session.title.trim();
  if (!raw || raw === "New agent") return "New agent";

  const clamp = raw.match(/clamp|math_utils/i);
  if (clamp) return "Clamp utility + tests";

  const testFix = raw.match(/fix.*test|failing test/i);
  if (testFix) return "Fix failing tests";

  const feature = raw.match(/^(add|create|implement|build|write)\s+/i);
  if (feature) {
    const stripped = raw
      .replace(/^(add|create|implement|build|write)\s+(a\s+)?(file\s+)?/i, "")
      .replace(/\s+with\s+.*/i, "")
      .trim();
    if (stripped.length > 0 && stripped.length <= 36) {
      return stripped.charAt(0).toUpperCase() + stripped.slice(1);
    }
  }

  if (raw.length <= 36) return raw;
  return `${raw.slice(0, 35)}…`;
}

export { TIME_BUCKET_ORDER };
