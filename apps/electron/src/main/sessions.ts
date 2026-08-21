import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import type { Session } from "../shared/events";

export function loadSessions(filePath: string): Session[] {
  try {
    if (!existsSync(filePath)) return [];
    const raw = JSON.parse(readFileSync(filePath, "utf8")) as Session[];
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

export function saveSessions(filePath: string, sessions: Session[]): void {
  mkdirSync(dirname(filePath), { recursive: true });
  writeFileSync(filePath, JSON.stringify(sessions, null, 2), "utf8");
}
