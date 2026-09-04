import { existsSync, mkdirSync } from "node:fs";
import { app, dialog } from "electron";
import { join } from "node:path";
import { gitBranch } from "../git";
import { PersistentStore } from "../lib/persistent-store";

type WorkspaceRecord = { path: string };

export class WorkspaceService {
  private workspace = "";
  private onChanged: ((path: string) => void) | null = null;
  private readonly store: PersistentStore<WorkspaceRecord>;

  constructor() {
    this.store = new PersistentStore<WorkspaceRecord>({
      filePath: join(app.getPath("userData"), "workspace.json"),
      scope: "workspace",
      emptyState: () => ({ path: "" }),
      serialize: (state) => state,
      deserialize: (raw) => {
        if (!raw || typeof raw !== "object") return null;
        const path = (raw as { path?: unknown }).path;
        return typeof path === "string" ? { path } : null;
      },
    });
  }

  setChangeHandler(handler: (path: string) => void): void {
    this.onChanged = handler;
  }

  get(): string {
    return this.workspace;
  }

  loadStored(): string {
    const record = this.store.loadFromStorage();
    this.workspace = record.path;
    return this.workspace;
  }

  async pick(): Promise<string> {
    const result = await dialog.showOpenDialog({
      title: "Open workspace",
      properties: ["openDirectory"],
    });
    if (result.canceled || !result.filePaths[0]) return this.workspace;
    const picked = result.filePaths[0];
    if (this.isMangoSource(picked)) {
      const isolated = join(app.getPath("userData"), "workspaces", "manual");
      mkdirSync(isolated, { recursive: true });
      this.workspace = isolated;
    } else {
      this.workspace = picked;
    }
    this.persistPath(this.workspace);
    this.onChanged?.(this.workspace);
    return this.workspace;
  }

  set(path: string): string {
    if (path) {
      this.workspace = path;
      this.persistPath(path);
      this.onChanged?.(path);
    }
    return this.workspace;
  }

  async branch(): Promise<string> {
    return gitBranch(this.workspace);
  }

  isMangoSource(path: string): boolean {
    return (
      existsSync(join(path, "runtime", "config.yaml")) &&
      existsSync(join(path, "agent", "python")) &&
      existsSync(join(path, "apps", "electron"))
    );
  }

  resolveAgentWorkspace(sessionId: string, requested?: string): string {
    for (const raw of [requested, this.workspace]) {
      if (!raw || this.isMangoSource(raw)) continue;
      mkdirSync(raw, { recursive: true });
      const resolved = raw;
      if (requested && resolved !== this.workspace) {
        this.workspace = resolved;
        this.persistPath(resolved);
        this.onChanged?.(resolved);
      }
      return resolved;
    }
    return this.isolate(sessionId);
  }

  adoptIfNeeded(used: string): void {
    if (!this.workspace || this.isMangoSource(this.workspace)) {
      this.workspace = used;
      this.persistPath(used);
    }
  }

  destroy(): void {
    this.store.destroy();
  }

  private isolate(sessionId: string): string {
    const isolated = join(app.getPath("userData"), "workspaces", sessionId || "default");
    mkdirSync(isolated, { recursive: true });
    return isolated;
  }

  private persistPath(path: string): void {
    this.store.replaceState({ path });
  }
}
