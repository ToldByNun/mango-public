import { app } from "electron";
import { join } from "node:path";
import type { Session } from "../../shared/events";
import { PersistentStore } from "../lib/persistent-store";

export class SessionService {
  private readonly store: PersistentStore<Session[]>;

  constructor() {
    this.store = new PersistentStore<Session[]>({
      filePath: join(app.getPath("userData"), "sessions.json"),
      scope: "sessions",
      emptyState: () => [],
      serialize: (sessions) => sessions,
      deserialize: (raw) => (Array.isArray(raw) ? (raw as Session[]) : null),
    });
  }

  path(): string {
    return join(app.getPath("userData"), "sessions.json");
  }

  load(): Session[] {
    return this.store.loadFromStorage();
  }

  list(): Session[] {
    return this.store.getState();
  }

  save(next: Session[]): Session[] {
    this.store.replaceState(next);
    return this.store.getState();
  }

  /** Immediate flush (prefer destroy on quit). */
  persist(): void {
    this.store.persistNow();
  }

  destroy(): void {
    this.store.destroy();
  }
}
