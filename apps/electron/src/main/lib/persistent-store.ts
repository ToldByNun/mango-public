/**
 * Debounced JSON persistence (FileQueue-style).
 * In-memory state + loadFromStorage / persistNow / debouncePersist / destroy.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { debug } from "./debug";

const DEFAULT_DEBOUNCE_MS = 1000;

export type PersistentStoreOptions<T> = {
  filePath: string;
  debounceMs?: number;
  /** Serialize in-memory state for disk. */
  serialize: (state: T) => unknown;
  /** Deserialize disk payload; return null to use emptyState. */
  deserialize: (raw: unknown) => T | null;
  emptyState: () => T;
  /** Optional crash-recovery / normalize after load. */
  recover?: (state: T) => T;
  scope?: string;
};

export class PersistentStore<T> {
  private state: T;
  private persistDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly filePath: string;
  private readonly debounceMs: number;
  private readonly serialize: (state: T) => unknown;
  private readonly deserialize: (raw: unknown) => T | null;
  private readonly emptyState: () => T;
  private readonly recover?: (state: T) => T;
  private readonly scope: string;
  private destroyed = false;

  constructor(options: PersistentStoreOptions<T>) {
    this.filePath = options.filePath;
    this.debounceMs = options.debounceMs ?? DEFAULT_DEBOUNCE_MS;
    this.serialize = options.serialize;
    this.deserialize = options.deserialize;
    this.emptyState = options.emptyState;
    this.recover = options.recover;
    this.scope = options.scope ?? "store";
    this.state = this.emptyState();
  }

  getState(): T {
    return this.state;
  }

  setState(next: T): void {
    this.state = next;
    this.debouncePersist();
  }

  /** Replace state and schedule debounced write. */
  replaceState(next: T): void {
    this.setState(next);
  }

  loadFromStorage(): T {
    try {
      if (!existsSync(this.filePath)) {
        this.state = this.emptyState();
        return this.state;
      }
      const rawText = readFileSync(this.filePath, "utf8");
      if (!rawText.trim()) {
        this.state = this.emptyState();
        return this.state;
      }
      const parsed = JSON.parse(rawText) as unknown;
      const loaded = this.deserialize(parsed);
      let next = loaded ?? this.emptyState();
      if (this.recover) {
        next = this.recover(next);
      }
      this.state = next;
      return this.state;
    } catch (error) {
      debug(this.scope, "loadFromStorage failed", error);
      this.state = this.emptyState();
      return this.state;
    }
  }

  persistNow(): void {
    if (this.persistDebounceTimer) {
      clearTimeout(this.persistDebounceTimer);
      this.persistDebounceTimer = null;
    }
    try {
      mkdirSync(dirname(this.filePath), { recursive: true });
      const payload = JSON.stringify(this.serialize(this.state), null, 2);
      writeFileSync(this.filePath, payload, "utf8");
    } catch (error) {
      debug(this.scope, "persistNow failed", error);
    }
  }

  debouncePersist(): void {
    if (this.destroyed) return;
    if (this.debounceMs <= 0) {
      this.persistNow();
      return;
    }
    if (this.persistDebounceTimer) {
      clearTimeout(this.persistDebounceTimer);
    }
    this.persistDebounceTimer = setTimeout(() => {
      this.persistDebounceTimer = null;
      this.persistNow();
    }, this.debounceMs);
  }

  /** Flush pending timer and write synchronously. */
  destroy(): void {
    this.destroyed = true;
    this.persistNow();
  }
}
