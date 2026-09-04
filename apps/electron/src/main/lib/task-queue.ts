/**
 * In-memory prioritized task queue with durable JSON backing (FileQueue pattern).
 */
import { PersistentStore } from "./persistent-store";

export type TaskStatus = "pending" | "running" | "success" | "failed";
export type TaskPriority = "high" | "normal" | "low";

export type QueueTask = {
  id: string;
  status: TaskStatus;
  priority: TaskPriority;
  retries: number;
  updatedAt: number;
  /** Legacy alias from upload examples — treated as running on load. */
  legacyStatus?: string;
  [key: string]: unknown;
};

const PRIORITY_RANK: Record<TaskPriority, number> = {
  high: 0,
  normal: 1,
  low: 2,
};

const MAX_BACKOFF_MS = 60_000;

export function computeBackoffMs(retries: number): number {
  const n = Math.max(0, Math.floor(retries));
  return Math.min(1000 * 2 ** n, MAX_BACKOFF_MS);
}

export type TaskQueueOptions = {
  filePath: string;
  debounceMs?: number;
  scope?: string;
};

export class TaskQueue {
  private readonly items = new Map<string, QueueTask>();
  private readonly store: PersistentStore<QueueTask[]>;

  constructor(options: TaskQueueOptions) {
    this.store = new PersistentStore<QueueTask[]>({
      filePath: options.filePath,
      debounceMs: options.debounceMs,
      scope: options.scope ?? "task-queue",
      emptyState: () => [],
      serialize: (tasks) => tasks,
      deserialize: (raw) => (Array.isArray(raw) ? (raw as QueueTask[]) : null),
      recover: (tasks) => tasks.map((task) => this.recoverTask(task)),
    });
  }

  loadFromStorage(): void {
    const tasks = this.store.loadFromStorage();
    this.items.clear();
    for (const task of tasks) {
      this.items.set(task.id, task);
    }
  }

  add(task: Omit<QueueTask, "updatedAt" | "retries"> & { retries?: number }): QueueTask {
    const next: QueueTask = {
      ...task,
      retries: task.retries ?? 0,
      updatedAt: Date.now(),
    };
    this.items.set(next.id, next);
    this.syncStore();
    return next;
  }

  addBatch(tasks: Array<Omit<QueueTask, "updatedAt" | "retries"> & { retries?: number }>): QueueTask[] {
    const added: QueueTask[] = [];
    for (const task of tasks) {
      added.push(this.add(task));
    }
    return added;
  }

  markAsPending(id: string): QueueTask | null {
    return this.markAs(id, "pending");
  }

  markAsRunning(id: string): QueueTask | null {
    return this.markAs(id, "running");
  }

  markAsSuccess(id: string): QueueTask | null {
    return this.markAs(id, "success");
  }

  markAsFailed(id: string, options?: { bumpRetry?: boolean }): QueueTask | null {
    const bumpRetry = options?.bumpRetry ?? true;
    const task = this.items.get(id);
    if (!task) return null;
    task.status = "failed";
    if (bumpRetry) task.retries += 1;
    task.updatedAt = Date.now();
    this.items.set(id, task);
    this.syncStore();
    return task;
  }

  get(id: string): QueueTask | undefined {
    return this.items.get(id);
  }

  getAll(): QueueTask[] {
    return [...this.items.values()];
  }

  getPending(): QueueTask[] {
    return this.getByStatus("pending");
  }

  getByStatus(status: TaskStatus): QueueTask[] {
    return this.getAll()
      .filter((t) => t.status === status)
      .sort((a, b) => PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] || a.updatedAt - b.updatedAt);
  }

  /**
   * Failed (or pending) tasks whose backoff window has elapsed.
   * Delay = min(1000 * 2^retries, 60000).
   */
  getRetryable(now = Date.now()): QueueTask[] {
    return this.getAll()
      .filter((task) => {
        if (task.status !== "failed" && task.status !== "pending") return false;
        if (task.status === "pending" && task.retries === 0) return true;
        const delay = computeBackoffMs(task.retries);
        return now - task.updatedAt >= delay;
      })
      .sort((a, b) => PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] || a.updatedAt - b.updatedAt);
  }

  persistNow(): void {
    this.syncStore(true);
  }

  destroy(): void {
    this.syncStore(true);
    this.store.destroy();
  }

  private markAs(id: string, status: TaskStatus): QueueTask | null {
    const task = this.items.get(id);
    if (!task) return null;
    task.status = status;
    task.updatedAt = Date.now();
    this.items.set(id, task);
    this.syncStore();
    return task;
  }

  private recoverTask(task: QueueTask): QueueTask {
    const status = String(task.status || task.legacyStatus || "pending");
    // Crash-recovery: in-flight work becomes pending again.
    if (status === "running" || status === "uploading") {
      return { ...task, status: "pending", updatedAt: Date.now() };
    }
    if (status === "pending" || status === "success" || status === "failed") {
      return { ...task, status };
    }
    return { ...task, status: "pending" };
  }

  private syncStore(immediate = false): void {
    const snapshot = this.getAll();
    if (immediate) {
      this.store.replaceState(snapshot);
      this.store.persistNow();
    } else {
      this.store.replaceState(snapshot);
    }
  }
}
